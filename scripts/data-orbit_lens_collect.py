#!/usr/bin/env python3
"""
通过 Platform Lens 批量收录 chat/segment 到 Platform 数据集

用法:
    # 单个 chat_id
    python data-orbit_lens_collect.py --dataset "my-benchmark" CHAT_ID

    # 多个 chat_id
    python data-orbit_lens_collect.py --dataset "my-benchmark" CHAT_ID1 CHAT_ID2

    # 从文件读取（每行一个 ID，# 开头为注释）
    python data-orbit_lens_collect.py --dataset "my-benchmark" --from-file chat_ids.txt

    # segment 模式
    python data-orbit_lens_collect.py --dataset "my-benchmark" --id-type segment SEGMENT_ID

    # share link 也行
    python data-orbit_lens_collect.py --dataset "my-benchmark" "https://www.AI_Platform.com/share/xxx"

    # 只提交不等待
    python data-orbit_lens_collect.py --dataset "my-benchmark" --no-poll CHAT_ID

    # Dry run
    python data-orbit_lens_collect.py --dataset "my-benchmark" --dry-run CHAT_ID
"""

import argparse
import atexit
import json
import os
import re
import sys
import time

import httpx

ORBIT_LENS_BASE = os.environ.get("ORBIT_LENS_BASE", "https://Platform-lens.internal.company.com")

HEADERS = {
    "X-AuthGateway-Access-Token": os.environ.get("AuthGateway_ACCESS_TOKEN", ""),
    "Content-Type": "application/json",
}

# 禁用代理，内网直连
HTTP_CLIENT = httpx.Client(trust_env=False, timeout=60)
atexit.register(HTTP_CLIENT.close)

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2.0


def resolve_share_link(input_str: str) -> str:
    """如果是 share link，提取 share_id 并提示；否则原样返回"""
    m = re.search(r"/share/([0-9a-zA-Z_-]+)", input_str)
    if m:
        share_id = m.group(1)
        print(f" 检测到 share link，share_id: {share_id}")
        print("   ️ Platform Lens 会自动处理 share link → chat_id 的转换")
        return share_id
    return input_str


def load_ids_from_file(filepath: str) -> list[str]:
    """从文件加载 ID 列表，跳过空行和 # 注释"""
    if not os.path.isfile(filepath):
        print(f" 文件不存在: {filepath}")
        sys.exit(1)
    ids = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            ids.append(line)
    return ids


def submit_batch_collect(dataset_name: str, chat_ids: list[str], id_type: str) -> str | None:
    """提交 batch-collect 请求，返回 jobId（带重试）"""
    url = f"{ORBIT_LENS_BASE}/api/langfuse/batch-collect"
    # chatIds 字段也兼容 share_id，Platform Lens API 侧会自动转换为 chat_id
    payload = {
        "datasetName": dataset_name,
        "chatIds": chat_ids,
        "idType": id_type,
    }

    print(" 提交 batch-collect 请求...")
    print(f"   Dataset: {dataset_name}")
    print(f"   ID type: {id_type}")
    print(f"   IDs count: {len(chat_ids)}")

    for attempt in range(MAX_RETRIES):
        try:
            response = HTTP_CLIENT.post(url, headers=HEADERS, json=payload)
            if response.status_code != 200:
                # 4xx 客户端错误不重试（除 429），只重试 5xx 和 429
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    print(f" HTTP {response.status_code}: {response.text[:300]}")
                    return None
                print(f"  ️ HTTP {response.status_code} (attempt {attempt + 1}/{MAX_RETRIES})")
                print(f"     {response.text[:300]}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                print(f" 提交失败（重试 {MAX_RETRIES} 次后）")
                return None

            try:
                data = response.json()
            except json.JSONDecodeError:
                print(f" 响应非 JSON: {response.text[:200]}")
                return None

            if not data.get("success"):
                print(f" 提交失败: {json.dumps(data, ensure_ascii=False)}")
                return None

            job_id = data.get("data", {}).get("jobId")
            if not job_id:
                print(f" 返回中无 jobId: {json.dumps(data, ensure_ascii=False)}")
                return None

            print(f" 提交成功，jobId: {job_id}")
            return job_id

        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            print(f"  ️ 网络异常 (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            print(f" 提交失败（重试 {MAX_RETRIES} 次后）")
            return None
        except Exception as e:
            print(f" 请求异常: {e}")
            return None

    return None


def poll_job(job_id: str, poll_interval: int, timeout: int) -> dict | None:
    """轮询 job 状态直到完成/失败/超时"""
    url = f"{ORBIT_LENS_BASE}/api/langfuse/batch-collect?jobId={job_id}"
    start_time = time.time()
    spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    spin_idx = 0

    print(f"\n 等待任务完成 (超时: {timeout}s, 间隔: {poll_interval}s)...")

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            print(f"\n 超时 ({timeout}s)，任务可能仍在运行")
            print(f"   jobId: {job_id}")
            print("   可稍后手动查询状态")
            return None

        try:
            response = HTTP_CLIENT.get(url, headers=HEADERS)
            if response.status_code != 200:
                print(f"\n️ 查询失败: HTTP {response.status_code}, 继续重试...")
                time.sleep(poll_interval)
                continue

            try:
                data = response.json()
            except json.JSONDecodeError:
                time.sleep(poll_interval)
                continue

            if not data.get("success"):
                time.sleep(poll_interval)
                continue

            job = data.get("data", {}).get("job", {})
            status = job.get("status", "unknown")
            total = job.get("totalCount", 0)
            processed = job.get("processedCount", 0)

            # 进度展示
            icon = spinner[spin_idx % len(spinner)]
            spin_idx += 1
            progress = f"{processed}/{total}" if total > 0 else "..."
            print(f"\r  {icon} [{status}] {progress} ({int(elapsed)}s)    ", end="", flush=True)

            if status == "completed":
                print()  # 换行
                return job
            elif status == "failed":
                print()  # 换行
                print(" 任务失败")
                return job

        except Exception as e:
            print(f"\n️ 轮询异常: {e}, 继续重试...")

        time.sleep(poll_interval)


def print_summary(job: dict):
    """打印最终结果摘要"""
    total = job.get("totalCount", 0)
    success_count = job.get("successCount", 0)
    failure_count = job.get("failureCount", 0)
    status = job.get("status", "unknown")
    results = job.get("results", [])

    print(f"\n{'=' * 50}")
    print(" 任务结果")
    print(f"{'=' * 50}")
    print(f"  状态:   {status}")
    print(f"  总数:   {total}")
    print(f"  成功:    {success_count}")
    print(f"  失败:    {failure_count}")

    # 打印失败详情
    failed = [r for r in results if not r.get("success")]
    if failed:
        print(f"\n{'─' * 50}")
        print(" 失败详情:")
        for r in failed:
            chat_id = r.get("chatId", "unknown")
            error = r.get("error", "unknown error")
            print(f"   {chat_id}: {error}")

    print(f"{'=' * 50}")


def main():
    parser = argparse.ArgumentParser(
        description="通过 Platform Lens 批量收录 chat/segment 到 Platform 数据集"
    )

    parser.add_argument("chat_ids", nargs="*", help="Chat IDs, segment IDs, 或 share links")
    parser.add_argument("--dataset", required=True, help="Platform 数据集名称")
    parser.add_argument("--from-file", help="从文件读取 ID（每行一个，# 开头为注释）")
    parser.add_argument("--id-type", choices=["chat", "segment"], default="chat", help="ID 类型 (默认: chat)")
    parser.add_argument("--no-poll", action="store_true", help="只提交不等待完成")
    parser.add_argument("--poll-interval", type=int, default=3, help="轮询间隔秒数 (默认: 3)")
    parser.add_argument("--timeout", type=int, default=300, help="最大等待秒数 (默认: 300)")
    parser.add_argument("--dry-run", action="store_true", help="只打印不实际提交")

    args = parser.parse_args()

    # 收集所有 IDs
    all_ids = list(args.chat_ids) if args.chat_ids else []

    if args.from_file:
        file_ids = load_ids_from_file(args.from_file)
        print(f" 从文件 {args.from_file} 读取了 {len(file_ids)} 个 ID")
        all_ids.extend(file_ids)

    if not all_ids:
        print(" 未提供任何 ID，请通过参数或 --from-file 传入")
        sys.exit(1)

    # 解析 share links + 保序去重
    resolved_ids = [resolve_share_link(id_str) for id_str in all_ids]
    dedup_count = len(resolved_ids)
    resolved_ids = list(dict.fromkeys(resolved_ids))
    if len(resolved_ids) < dedup_count:
        print(f"️ 去重: {dedup_count} → {len(resolved_ids)} 个唯一 ID")

    print(f"\n 待收录 {len(resolved_ids)} 个 {args.id_type}(s) → 数据集 \"{args.dataset}\"")
    for i, id_str in enumerate(resolved_ids):
        print(f"  {i + 1}. {id_str}")

    # Dry run
    if args.dry_run:
        print("\n️ Dry run 模式，不实际提交")
        print(f"   POST {ORBIT_LENS_BASE}/api/langfuse/batch-collect")
        print(f"   Body: {json.dumps({'datasetName': args.dataset, 'chatIds': resolved_ids, 'idType': args.id_type}, ensure_ascii=False, indent=2)}")
        sys.exit(0)

    # 检查 token
    if not HEADERS["X-AuthGateway-Access-Token"]:
        print(" 未设置 AuthGateway_ACCESS_TOKEN 环境变量")
        sys.exit(1)

    # 提交
    job_id = submit_batch_collect(args.dataset, resolved_ids, args.id_type)
    if not job_id:
        sys.exit(1)

    # 不等待
    if args.no_poll:
        print("\n 已提交，跳过轮询 (--no-poll)")
        print(f"   jobId: {job_id}")
        print(f"   可手动查询: GET {ORBIT_LENS_BASE}/api/langfuse/batch-collect?jobId={job_id}")
        sys.exit(0)

    # 轮询
    job = poll_job(job_id, args.poll_interval, args.timeout)
    if not job:
        sys.exit(1)

    # 打印摘要
    print_summary(job)

    # 退出码
    failure_count = job.get("failureCount", 0)
    sys.exit(1 if failure_count > 0 else 0)


if __name__ == "__main__":
    main()
