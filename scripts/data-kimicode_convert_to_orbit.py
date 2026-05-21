#!/usr/bin/env python3
"""data-kimicode_convert_to_orbit.py  将 AI_Code_Platform (Internal_AI_Service) 请求日志转为 Platform Dataset JSONL 格式

将日志中的 request.messages 作为 query（Input），其余元信息作为 Metadata。

用法:
    python scripts/data-kimicode_convert_to_orbit.py input.jsonl [output.jsonl]

输入: Internal_AI_Service导出的 JSONL（每行含 request / response / model_id 等字段）
输出: Platform Dataset JSONL（query + metadata 字段）
"""

import json
import sys
from pathlib import Path


def convert(input_path: str, output_path: str):
    with open(input_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]

    records = []
    skipped = 0
    for d in lines:
        req = json.loads(d.get("request", "{}")) if d.get("request") else {}
        messages = req.get("messages", [])
        if not messages:
            skipped += 1
            continue

        record = {
            # Input field
            "query": json.dumps(messages, ensure_ascii=False),
            # Metadata fields
            "original_id": d.get("id", ""),
            "model_id": d.get("model_id", ""),
            "finish_reason": d.get("finish_reason", ""),
            "prompt_tokens": d.get("prompt_tokens", 0),
            "conversation_id": d.get("conversation_id", ""),
            "client_user": d.get("client_user", ""),
            "codegw_client_type": d.get("codegw_client_type", ""),
            "created_at": d.get("created_at", ""),
            "trace_id": d.get("trace_id", ""),
            "num_messages": len(messages),
            "num_user_turns": sum(1 for m in messages if m.get("role") == "user"),
        }
        records.append(record)

    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f" 转换完成: {len(records)} 条 → {output_path}")
    if skipped:
        print(f"️  跳过 {skipped} 条（无 messages）")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/data-kimicode_convert_to_orbit.py input.jsonl [output.jsonl]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(input_file).with_stem(Path(input_file).stem + "_orbit")
    )
    convert(input_file, output_file)
