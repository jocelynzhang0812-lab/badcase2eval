"""
Ask LLM - 使用 LLM API 对 JSONL 数据批量打标/分类

通过环境变量配置 API：
    LLM_API_KEY   - API 密钥（必需）
    LLM_API_BASE  - API 地址（默认 https://api.openai.com/v1）
    LLM_MODEL     - 默认模型（默认 gpt-4o-mini）

用法:
    python ask_llm.py -p prompt.txt -i input.jsonl -o output.jsonl -c 32
"""

import click
import json
import re
import os
import sys
import asyncio
import aiohttp
import threading
from tqdm import tqdm
from tenacity import retry, stop_never, wait_exponential, retry_if_exception_type
from loguru import logger

# ---------- 从环境变量读取配置 ----------
API_KEY = os.environ.get("LLM_API_KEY", "")
API_BASE = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/")
DEFAULT_MODEL_NAME = os.environ.get("LLM_MODEL", "gpt-4o-mini")


def render_prompt(template: str, record: dict) -> str:
    """渲染 prompt 模板，将 {key} 替换为对应字段值"""
    result = template
    for key, value in record.items():
        result = result.replace(f"{{{key}}}", str(value) if value is not None else "")
    return result


def extract_json_from_response(text: str) -> dict | None:
    """从 API 返回的文本中提取 JSON 对象"""
    # 先尝试从 markdown 代码块中提取
    md_pattern = r"```(?:json)?\s*([\s\S]*?)```"
    md_matches = re.findall(md_pattern, text)
    for m in md_matches:
        obj = json.loads(m.strip())
        return obj

    # 尝试匹配任意 JSON 对象
    json_pattern = r"\{[\s\S]*\}"
    matches = re.findall(json_pattern, text)
    for m in matches:
        obj = json.loads(m)
        return obj

    raise APIError(f"未找到 JSON 对象: {text}")


class APIError(Exception):
    """API 调用错误，用于触发重试"""
    pass


def log_retry(retry_state):
    """记录重试日志"""
    logger.warning(
        f"重试第 {retry_state.attempt_number} 次，"
        f"等待 {retry_state.next_action.sleep:.1f}s，"
        f"错误: {retry_state.outcome.exception()}"
    )


@retry(
    stop=stop_never,
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(APIError),
    before_sleep=log_retry
)
async def call_api_with_retry(session: aiohttp.ClientSession, prompt: str, model_name: str, temperature: float = 0.3, max_tokens: int = 1024) -> str:
    """调用 API 获取打标结果，带重试机制"""
    api_url = f"{API_BASE}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        async with session.post(api_url, json=payload) as response:
            if response.status == 200:
                result = await response.json()
                content = result["choices"][0]["message"]["content"]
                logger.info(f"API 返回内容: {content}")
                label_result = extract_json_from_response(content)
                return label_result
            else:
                error_text = await response.text()
                raise APIError(f"API error {response.status}: {error_text[:200]}")
    except aiohttp.ClientError as e:
        raise APIError(f"Request error: {e}")
    except asyncio.TimeoutError:
        raise APIError("Request timeout")
    except KeyError as e:
        raise APIError(f"Invalid response format: {e}")


async def process_record(session: aiohttp.ClientSession, template: str, record: dict, idx: int, model_name: str, max_tokens: int) -> dict:
    """处理单条记录：渲染 prompt、调用 API、提取结果"""
    prompt = render_prompt(template, record)
    result = record.copy()

    try:
        label_result = await call_api_with_retry(session, prompt, model_name, max_tokens=max_tokens)
        if label_result:
            result.update(label_result)
        else:
            result["_error"] = "Failed to extract JSON from response"
            result["_raw_response"] = label_result
    except Exception as e:
        result["_error"] = f"Unexpected error: {e}"

    return result


def load_completed_urls(output_file: str) -> set:
    """从已有的输出文件中加载已完成的 URL 集合"""
    completed = set()
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if "url" in record:
                        completed.add(record["url"])
                except json.JSONDecodeError:
                    continue
    return completed


class OutputWriter:
    """线程安全的输出写入器，支持实时写入"""
    def __init__(self, output_file: str, append: bool = False):
        self.output_file = output_file
        self.lock = threading.Lock()
        mode = "a" if append else "w"
        self.file = open(output_file, mode, encoding="utf-8")

    def write(self, record: dict):
        with self.lock:
            self.file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.file.flush()

    def close(self):
        self.file.close()


async def process_batch(template: str, records: list[dict], concurrency: int, model_name: str, max_tokens: int, writer: OutputWriter) -> int:
    """批量处理记录，实时写入结果"""
    semaphore = asyncio.Semaphore(concurrency)
    completed_count = 0

    async def bounded_process(session, template, record, idx):
        async with semaphore:
            result = await process_record(session, template, record, idx, model_name, max_tokens)
            writer.write(result)
            return result

    async with aiohttp.ClientSession(
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        },
        timeout=aiohttp.ClientTimeout(total=300)
    ) as session:
        tasks = [
            bounded_process(session, template, record, idx)
            for idx, record in enumerate(records)
        ]

        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Processing"):
            await coro
            completed_count += 1

    return completed_count


@click.command()
@click.option("-p", "--prompt-template", "prompt_template", type=click.Path(exists=True), required=True, help="Prompt 模板文件路径")
@click.option("-i", "--input", "input_file", type=click.Path(exists=True), required=True, help="输入 JSONL 文件路径")
@click.option("-o", "--output", "output_file", type=click.Path(), required=True, help="输出 JSONL 文件路径")
@click.option("-m", "--model", "model_name", type=str, default=DEFAULT_MODEL_NAME, help="模型名称")
@click.option("-c", "--concurrency", type=int, default=16, help="并发请求数")
@click.option("-l", "--limit", type=int, default=None, help="限制处理条数（用于测试）")
@click.option("--max-chars", type=int, default=1000, help="text 字段最大字符数，超过则截断（默认 1000，设为 0 或负数禁用截断）")
@click.option("--max-tokens", type=int, default=4096, help="API 返回的最大 token 数（默认 4096）")
@click.option("--continue", "continue_mode", is_flag=True, default=False, help="断点续传模式，跳过已完成的记录")
def main(prompt_template, input_file, output_file, model_name, concurrency, limit, max_chars, max_tokens, continue_mode):
    """调用 LLM API 对数据进行自动打标"""

    # 检查 API Key
    if not API_KEY:
        logger.error("未设置 LLM_API_KEY 环境变量。请先运行: export LLM_API_KEY='your-api-key'")
        sys.exit(1)

    logger.info(f"API 地址: {API_BASE}")
    logger.info(f"使用模型: {model_name}")
    logger.info(f"最大 tokens: {max_tokens}")

    # 读取 prompt 模板
    with open(prompt_template, "r", encoding="utf-8") as f:
        template = f.read()

    # 检查模板中的占位符
    keys = re.findall(r"\{(\w+)\}", template)
    logger.info(f"模板中的占位符: {keys}")

    # 读取输入数据
    records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    logger.info(f"读取了 {len(records)} 条记录")

    # 检查所有占位符都在数据中
    if records:
        sample_keys = set(records[0].keys())
        missing_keys = [k for k in keys if k not in sample_keys]
        if missing_keys:
            raise click.ClickException(f"输入数据缺少占位符字段: {missing_keys}")

    # 限制处理条数
    if limit:
        records = records[:limit]
        logger.info(f"限制处理 {limit} 条记录")

    # 断点续传：加载已完成的 URL
    completed_urls = set()
    if continue_mode:
        completed_urls = load_completed_urls(output_file)
        if completed_urls:
            logger.info(f"断点续传模式：已完成 {len(completed_urls)} 条记录")
            original_count = len(records)
            records = [r for r in records if r.get("url") not in completed_urls]
            logger.info(f"跳过已完成记录，剩余 {len(records)} 条待处理（原 {original_count} 条）")

    if not records:
        logger.success("所有记录已完成，无需处理")
        return

    # 截断 text 字段
    if max_chars and max_chars > 0:
        truncated_count = 0
        for record in records:
            if "text" in record and record["text"] and len(record["text"]) > max_chars:
                record["text"] = record["text"][:max_chars]
                truncated_count += 1
        if truncated_count > 0:
            logger.info(f"已截断 {truncated_count} 条记录的 text 字段（最大 {max_chars} 字符）")

    # 创建输出写入器（断点续传模式下追加写入）
    writer = OutputWriter(output_file, append=continue_mode)

    try:
        completed = asyncio.run(process_batch(template, records, concurrency, model_name, max_tokens, writer))
        logger.success(f"处理完成，共 {completed} 条记录已保存到 {output_file}")
    finally:
        writer.close()


if __name__ == "__main__":
    main()
