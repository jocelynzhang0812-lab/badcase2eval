#!/usr/bin/env python3
"""
拉取指定 chat_id 下的所有 Chatlet Workflow Semantic Trace 数据。

用法:
    python fetch_chat_requests.py <chat_id> [--env dev|prod] [--output <dir>]

示例:
    python fetch_chat_requests.py 19d229c2-f8b2-82fb-8000-09001d2876e7 --env dev
    python fetch_chat_requests.py <chat_id> --env prod -o output/

需要环境变量:
    AuthGateway_ACCESS_TOKEN: AuthGateway 访问令牌
"""

import argparse
import httpx
import json
import os
import sys

from kimi_python.chatlet.v2.chatlet_pb2 import ListMessagesRequest
from kimi_python.chatlet.v2.chatlet_connect import ChatletServiceClientSync

ENDPOINTS = {
    "dev": "https://chatlet.dev.AI_Platform.team/api",
    "prod": "https://internal.company.com/api",
}


def list_all_messages(client, chat_id, headers):
    """分页拉取指定 chat_id 下的所有消息（VIEW_FULL 包含 trace URL）"""
    all_entries = []
    page_token = ""

    while True:
        request = ListMessagesRequest(
            chat_id=chat_id,
            page_size=100,
            view=2,  # VIEW_FULL
            page_token=page_token,
        )
        response = client.list_messages(request, headers=headers)
        all_entries.extend(response.message_entries)
        print(f"  拉取到 {len(response.message_entries)} 条消息", file=sys.stderr)

        if not response.next_page_token:
            break
        page_token = response.next_page_token

    return all_entries


def fetch_trace_data(http_client, base_url, trace_id, headers):
    """拉取单个 trace 的 semantic 数据"""
    url = f"{base_url}/traces:semantic/{trace_id}"
    resp = http_client.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="拉取指定 chat_id 的所有 request 数据")
    parser.add_argument("chat_id", help="Chatlet chat_id")
    parser.add_argument("--env", choices=["dev", "prod"], default="dev", help="环境 (默认: dev)")
    parser.add_argument("--output", "-o", default=".", help="输出目录 (默认: 当前目录)")
    args = parser.parse_args()

    token = os.environ.get("AuthGateway_ACCESS_TOKEN")
    if not token:
        print("错误: 需要设置 AuthGateway_ACCESS_TOKEN 环境变量", file=sys.stderr)
        sys.exit(1)

    endpoint = ENDPOINTS[args.env]
    headers = {"X-AuthGateway-Access-Token": token}
    os.makedirs(args.output, exist_ok=True)

    print(f"环境: {args.env} ({endpoint})", file=sys.stderr)
    print(f"Chat ID: {args.chat_id}", file=sys.stderr)

    # Step 1: 拉取所有消息
    print("\n[Step 1] 拉取消息列表...", file=sys.stderr)
    rpc_client = ChatletServiceClientSync(endpoint)
    entries = list_all_messages(rpc_client, args.chat_id, headers)
    print(f"  共 {len(entries)} 条消息", file=sys.stderr)

    # Step 2: 提取去重的 trace IDs
    trace_ids = set()
    for entry in entries:
        if entry.trace_semantic_url:
            tid = entry.trace_semantic_url.split("/")[-1]
            trace_ids.add(tid)

    print(f"\n[Step 2] 发现 {len(trace_ids)} 个唯一 trace", file=sys.stderr)

    if not trace_ids:
        print("未找到任何 trace 数据", file=sys.stderr)
        sys.exit(0)

    # Step 3: 拉取每个 trace 的 semantic 数据
    print("\n[Step 3] 拉取 trace 数据...", file=sys.stderr)
    all_traces = []

    with httpx.Client(timeout=60) as http_client:
        for i, tid in enumerate(sorted(trace_ids)):
            print(f"  [{i+1}/{len(trace_ids)}] trace_id={tid}", file=sys.stderr)
            try:
                data = fetch_trace_data(http_client, endpoint, tid, headers)
                all_traces.append(data)

                # 保存单个 trace
                trace_file = os.path.join(args.output, f"trace_{tid}.json")
                with open(trace_file, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"    → {trace_file}", file=sys.stderr)

                # 打印摘要
                for wf in data.get("workflows", []):
                    meta = wf.get("meta", {})
                    wf_name = meta.get("name", "N/A")
                    complete = meta.get("complete", False)
                    for pl in wf.get("pipelines", []):
                        steps = pl.get("steps", [])
                        model_steps = [s for s in steps if s.get("kind") == "KIND_MODEL_REQUEST"]
                        print(
                            f"    workflow={wf_name}, complete={complete}, "
                            f"pipeline={pl.get('name')}, "
                            f"total_steps={len(steps)}, model_requests={len(model_steps)}",
                            file=sys.stderr,
                        )
            except Exception as e:
                print(f"     失败: {e}", file=sys.stderr)

    # 保存汇总文件
    summary_file = os.path.join(args.output, f"chat_{args.chat_id}_all_traces.json")
    with open(summary_file, "w") as f:
        json.dump(all_traces, f, indent=2, ensure_ascii=False)

    print(f"\n完成！共 {len(all_traces)} 个 trace 已保存", file=sys.stderr)
    print(f"汇总文件: {summary_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
