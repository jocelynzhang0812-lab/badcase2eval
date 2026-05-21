#!/usr/bin/env python3
"""
fact_check_judge.py  对模型回复进行事实核查

基于 moonfaith FactAgentAPI，从模型回复中提取事实声明，逐条核查真实性。
可与 judge.py 配合使用：judge.py 打质量分，本脚本打事实准确率。

用法:
    python scripts/fact_check_judge.py bmk/output_dir \
        --bmk bmk/dataset.csv \
        --model ai_service/claude-3-5-sonnet \
        -j 5 \
        --limit 10

依赖:
    pip install moonfaith --extra-index-url https://internal.company.com/simple

环境变量:
    SEARCH_GRPC_TOKEN   搜索 token（必需）
    OPENAI_API_KEY     API key（提取 claims 用）

输出: fact_check_result/{bmk_stem}.xlsx
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

# ---------- 配置 ----------

# SEARCH_GRPC_TOKEN fallback 到 SEARCH_TOKEN（同一个 token，不同变量名）
if not os.environ.get("SEARCH_GRPC_TOKEN") and os.environ.get("SEARCH_TOKEN"):
    os.environ["SEARCH_GRPC_TOKEN"] = os.environ["SEARCH_TOKEN"]

# 提取 claims 的 LLM 配置
EXTRACT_MODEL = os.environ.get("FACT_CHECK_EXTRACT_MODEL", "ai_service/claude-3-5-sonnet")
EXTRACT_BASE_URL = "https://gateway.internal.ai.com/v1"
EXTRACT_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# FactCheck 配置
FACT_CHECK_MODEL = os.environ.setdefault("SEARCH_GRPC_TOKEN", os.environ.get("SEARCH_TOKEN", ""))

os.environ.get("FACT_CHECK_MODEL", "ai_service/claude-3-5-sonnet")
FACT_CHECK_MAX_STEPS = 5
FACT_CHECK_TEMPERATURE = 0.0

# 并发
MAX_CONCURRENCY = 5

# 清除代理（内网服务）
for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(k, None)

# ---------- Claims 提取 ----------

EXTRACT_CLAIMS_PROMPT = """请从以下文本中提取所有可以通过搜索验证的事实声明（factual claims）。

要求：
1. 只提取客观事实声明，跳过主观观点、建议、推测
2. 每条声明应该是独立的、可验证的
3. 跳过过于泛泛的常识（如"太阳从东方升起"）
4. 保留具体的数字、日期、人名、事件等关键信息
5. 如果文本中没有可验证的事实声明，返回空列表

输出格式（严格 JSON）：
{"claims": ["声明1", "声明2", ...]}

如果没有可验证的声明：
{"claims": []}

文本：
{text}"""


async def extract_claims(text: str, client) -> list[str]:
    """用 LLM 从文本中提取可验证的事实声明"""
    if not text or len(text.strip()) < 20:
        return []

    # 截断过长的文本
    if len(text) > 8000:
        text = text[:8000] + "\n...(截断)"

    try:
        response = await client.chat.completions.create(
            model=EXTRACT_MODEL,
            messages=[{"role": "user", "content": EXTRACT_CLAIMS_PROMPT.format(text=text)}],
            temperature=0.0,
            max_tokens=2000,
        )
        content = response.choices[0].message.content.strip()

        # 解析 JSON
        # 尝试直接解析
        try:
            data = json.loads(content)
            return data.get("claims", [])
        except json.JSONDecodeError:
            # 尝试从 markdown code block 中提取
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                return data.get("claims", [])
            # 尝试找 JSON 对象
            match = re.search(r"\{.*\"claims\".*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data.get("claims", [])
            print(f"  ️ 无法解析 claims JSON: {content[:200]}")
            return []
    except Exception as e:
        print(f"  ️ 提取 claims 失败: {e}")
        return []


# ---------- 模型回复提取 ----------

def extract_model_response(result: dict) -> str:
    """从 batch 输出 JSON 中提取模型最终回复文本"""
    final = ""
    for event in result.get("output", []):
        if event.get("type") == "model_end":
            for c in event.get("message", {}).get("contents", []):
                text = (c.get("text") or "").strip()
                if text:
                    final = text
    return final


# ---------- 主流程 ----------

async def fact_check_single(
    index: int,
    result: dict,
    query: str,
    fact_agent,
    extract_client,
    semaphore: asyncio.Semaphore,
) -> dict:
    """对单条结果进行事实核查"""
    async with semaphore:
        response_text = extract_model_response(result)
        if not response_text:
            return {
                "index": index,
                "query": query,
                "response": "",
                "claims": [],
                "results": [],
                "fact_score": None,
                "error": "空回复",
            }

        print(f"  [{index}] 提取 claims...")
        claims = await extract_claims(response_text, extract_client)

        if not claims:
            return {
                "index": index,
                "query": query,
                "response": response_text[:500],
                "claims": [],
                "results": [],
                "fact_score": None,
                "note": "无可验证的事实声明",
            }

        print(f"  [{index}] 核查 {len(claims)} 条 claims...")
        try:
            check_results = await fact_agent.check_claims(claims)
        except Exception as e:
            return {
                "index": index,
                "query": query,
                "response": response_text[:500],
                "claims": claims,
                "results": [],
                "fact_score": None,
                "error": f"核查失败: {e}",
            }

        # 统计
        label_counts = {}
        details = []
        for r in check_results:
            label = r.label if r.success else "ERROR"
            label_counts[label] = label_counts.get(label, 0) + 1
            details.append({
                "claim": r.claim,
                "label": label,
                "explanation": r.explanation if r.success else r.error,
            })

        verifiable = sum(
            1 for r in check_results
            if r.success and r.label != "NON-VERIFIABLE"
        )
        supported = sum(
            1 for r in check_results
            if r.success and r.label == "SUPPORTED"
        )
        fact_score = supported / verifiable if verifiable > 0 else None

        status = f" {supported}/{verifiable}" if fact_score and fact_score >= 0.8 else f"️ {supported}/{verifiable}"
        print(f"  [{index}] {status} (fact_score={fact_score:.2f})" if fact_score is not None else f"  [{index}] 无可验证声明")

        return {
            "index": index,
            "query": query,
            "response": response_text[:500],
            "claims": claims,
            "results": details,
            "label_counts": label_counts,
            "claims_total": len(claims),
            "verifiable": verifiable,
            "supported": supported,
            "fact_score": fact_score,
        }


async def main():
    parser = argparse.ArgumentParser(description="模型回复事实核查")
    parser.add_argument("batch_dir", help="batch 输出目录（含 0.json, 1.json, ...）")
    parser.add_argument("--bmk", help="BMK 文件（CSV/Excel），用于读取 query")
    parser.add_argument("--model", default=FACT_CHECK_MODEL, help="FactCheck 使用的模型")
    parser.add_argument("-j", "--concurrency", type=int, default=MAX_CONCURRENCY, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条")
    parser.add_argument("-o", "--output", default=None, help="输出路径")
    args = parser.parse_args()

    batch_dir = Path(args.batch_dir)
    if not batch_dir.exists():
        print(f" 目录不存在: {batch_dir}")
        sys.exit(1)

    # 读取 batch 结果
    result_files = sorted(batch_dir.glob("*.json"), key=lambda f: int(f.stem) if f.stem.isdigit() else 0)
    if args.limit:
        result_files = result_files[: args.limit]
    print(f" 读取 {len(result_files)} 条结果: {batch_dir}")

    results = []
    for f in result_files:
        with open(f) as fh:
            results.append(json.load(fh))

    # 读取 BMK 获取 query（可选）
    queries = {}
    if args.bmk:
        bmk_path = Path(args.bmk)
        if bmk_path.suffix in (".xlsx", ".xls"):
            import pandas as pd
            df = pd.read_excel(bmk_path)
            for i, row in df.iterrows():
                queries[i] = row.get("query", "")
        else:
            import csv
            with open(bmk_path, encoding="utf-8") as f:
                for i, row in enumerate(csv.DictReader(f)):
                    queries[i] = row.get("query", "")

    # 初始化 moonfaith
    from moonfaith import FactAgentAPI

    fact_agent = FactAgentAPI(
        model=args.model,
        api_key=EXTRACT_API_KEY or None,
        temperature=FACT_CHECK_TEMPERATURE,
        max_steps=FACT_CHECK_MAX_STEPS,
        max_tokens=64000,
        tool_call_concurrency=10,
        thinking=False,
    )

    # 初始化提取 claims 的 LLM client
    from openai import AsyncOpenAI

    extract_client = AsyncOpenAI(
        api_key=EXTRACT_API_KEY or "sk-placeholder",
        base_url=EXTRACT_BASE_URL,
    )

    # 并发执行
    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = []
    for i, result in enumerate(results):
        query = queries.get(i, result.get("query", f"[row {i}]"))
        tasks.append(fact_check_single(i, result, query, fact_agent, extract_client, semaphore))

    print(f"\n 开始事实核查（{len(tasks)} 条，并发 {args.concurrency}）...\n")
    all_results = await asyncio.gather(*tasks)

    # 汇总统计
    total = len(all_results)
    scored = [r for r in all_results if r.get("fact_score") is not None]
    if scored:
        avg_score = sum(r["fact_score"] for r in scored) / len(scored)
        print(f"\n{'=' * 50}")
        print(" 事实核查汇总")
        print(f"   总条数: {total}")
        print(f"   有效评分: {len(scored)}")
        print(f"   平均事实准确率: {avg_score:.1%}")
        print(f"   准确率 ≥ 80%: {sum(1 for r in scored if r['fact_score'] >= 0.8)}")
        print(f"   准确率 < 50%: {sum(1 for r in scored if r['fact_score'] < 0.5)}")
        print(f"{'=' * 50}")

    # 输出 Excel
    try:
        import pandas as pd

        output_path = args.output or f"fact_check_result/{Path(args.bmk).stem if args.bmk else batch_dir.name}.xlsx"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for r in all_results:
            rows.append({
                "index": r["index"],
                "query": r.get("query", "")[:200],
                "response": r.get("response", "")[:300],
                "claims_total": r.get("claims_total", 0),
                "verifiable": r.get("verifiable", 0),
                "supported": r.get("supported", 0),
                "fact_score": r.get("fact_score"),
                "claims": json.dumps(r.get("claims", []), ensure_ascii=False)[:500],
                "details": json.dumps(r.get("results", []), ensure_ascii=False)[:1000],
                "error": r.get("error", ""),
            })

        df = pd.DataFrame(rows)
        df.to_excel(output_path, index=False)
        print(f"\n 结果已保存: {output_path}")

    except ImportError:
        # 没有 pandas，输出 JSONL
        output_path = args.output or f"fact_check_result/{batch_dir.name}.jsonl"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for r in all_results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n 结果已保存: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
