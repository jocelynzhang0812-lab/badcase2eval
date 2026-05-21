#!/usr/bin/env python3
"""badcase_to_orbit.py  从 badcase 收录表 + trace 目录生成 Platform 数据集

前提：已用 get_message.py 拉取了每个 chat_id 的 trace

用法:
    python scripts/badcase_to_orbit.py model_bad_case.csv [output.jsonl]
"""

import csv
import json
import sys
from pathlib import Path

TRACE_DIR = Path("chatlet/trace")


def extract_query_from_trace(chat_id: str, turn_step: str) -> str | None:
    """从 trace JSON 中提取指定 turn-step 的 user query"""
    trace_file = TRACE_DIR / f"{chat_id}.json"
    if not trace_file.exists():
        print(f"️  trace 不存在: {trace_file}")
        return None

    with open(trace_file) as f:
        trace = json.load(f)

    parts = turn_step.split("-")
    if len(parts) != 2:
        print(f"️  turn_step 格式错误: {turn_step}（应为 turn-step，如 22-1）")
        return None

    turn, step = int(parts[0]), int(parts[1])  # noqa: F841

    turns = trace.get("turns", [])
    if turn >= len(turns):
        print(f"️  turn {turn} 超出范围 (共 {len(turns)} 轮)")
        return None

    messages = turns[turn].get("messages", [])
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        return item.get("text", "")
            elif isinstance(content, str):
                return content
    return None


def convert_badcase(badcase_csv: str, output_jsonl: str):
    with open(badcase_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    records = []
    missing_traces = []
    for row in rows:
        chat_id = row.get("chat_id", "").strip()
        turn_step = row.get("problem_turn_step", "").strip()
        scenario = row.get("scenario", "").strip()
        judge_comment = row.get("judge", "").strip()

        query = extract_query_from_trace(chat_id, turn_step)
        if not query:
            missing_traces.append(chat_id)
            continue

        records.append({
            "query": query,
            "rubric": judge_comment,
            "scenario": scenario,
            "source_chat_id": chat_id,
            "source_turn_step": turn_step,
        })

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f" 转换完成: {len(records)} 条 → {output_jsonl}")
    if missing_traces:
        print(f"️  {len(missing_traces)} 条缺少 trace，需先拉取:")
        for cid in missing_traces[:5]:
            print(f"   python get_message.py --prod --trace {cid}")
        if len(missing_traces) > 5:
            print(f"   ... 还有 {len(missing_traces) - 5} 条")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/badcase_to_orbit.py model_bad_case.csv [output.jsonl]")
        print("前提: 已在 chatlet/trace/ 下拉取了对应的 trace 文件")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "orbit_dataset.jsonl"
    convert_badcase(input_path, output_path)
