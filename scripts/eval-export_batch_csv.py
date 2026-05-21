#!/usr/bin/env python3
"""eval-export_batch_csv.py  将 Platform batch 导出的 JSONL 格式化为 7 列 CSV。

输出列：query, keypoint, baseline, eval, judge_result_answer, judge_result_toolcall, judge

用法：
  # 先用 Platform CLI 导出 JSONL
  node Platform/Platform.mjs export --batch <batchId>

  # 再转 CSV
  python scripts/eval-export_batch_csv.py batch_<batchId>_export.jsonl -o batch_<batchId>.csv

  # 也支持 stdin
  cat batch_123.jsonl | python scripts/eval-export_batch_csv.py -o batch_123.csv

注意事项：
  - query 输出为 JSON 格式 [{"text": "..."}]，方便导入[Internal Docs Platform]表格
  - 兼容 content 为字符串或列表两种格式
  - judge 默认值为 Equal（无 CATEGORICAL 分数时）
"""

import argparse
import json
import sys


def escape_csv(text: str) -> str:
    """Escape a field for CSV output."""
    if not text:
        return ""
    text = str(text)
    needs_quoting = "," in text or "\n" in text or '"' in text
    text = text.replace('"', '""')
    if needs_quoting:
        return f'"{text}"'
    return text


def extract_query(trace_input: dict) -> str:
    """Extract user query text from traceInput.messages."""
    msgs = trace_input.get("messages", []) or []
    for m in msgs:
        if m.get("role") != "user":
            continue
        content = m.get("content", [])
        if isinstance(content, str):
            if len(content) > 15:
                return content
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    t = item.get("text", "")
                    if len(t) > 15 and "<upload" not in t and "<image" not in t:
                        return t
    return ""


def extract_eval_output(trace_output: dict) -> str:
    """Extract model output from traceOutput.final_output.content."""
    fo = (trace_output or {}).get("final_output", {}) or {}
    content = fo.get("content", [])
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
    return ""


def extract_scores(scores: list) -> tuple[str, str, str]:
    """Extract judge_result_answer, judge_result_toolcall, judge from scores."""
    judge_result_answer = ""
    judge_result_toolcall = ""
    judge = "Equal"

    for s in scores or []:
        name = s.get("name", "")
        value = s.get("value", "")
        comment = s.get("comment", "") or ""

        if s.get("dataType") == "CATEGORICAL":
            if value in ("Better", "Worse", "Equal"):
                judge = value
            elif s.get("stringValue") in ("Better", "Worse", "Equal"):
                judge = s.get("stringValue")
            judge_result_answer = comment if comment else f"{name}: {value}"
        elif "Toolcall" in name:
            entry = f"{name}: {value}\n{comment}" if comment else f"{name}: {value}"
            if judge_result_toolcall:
                judge_result_toolcall += "\n"
            judge_result_toolcall += entry

    return judge_result_answer, judge_result_toolcall, judge


def process_line(line: str) -> str:
    """Process a single JSONL line into a CSV row."""
    d = json.loads(line)

    ti = d.get("traceInput", {}) or {}
    to = d.get("traceOutput", {}) or {}

    query_text = extract_query(ti)
    query_json = json.dumps([{"text": query_text}], ensure_ascii=False) if query_text else '[{"text": ""}]'

    keypoint = ti.get("key_point", "")
    baseline = ti.get("baseline_model_response", "")
    eval_text = extract_eval_output(to)
    judge_answer, judge_toolcall, judge = extract_scores(d.get("scores", []))

    fields = [query_json, keypoint, baseline, eval_text, judge_answer, judge_toolcall, judge]
    return ",".join(escape_csv(f) for f in fields)


def main():
    parser = argparse.ArgumentParser(
        description="将 Platform batch JSONL 格式化为 7 列 CSV（query/keypoint/baseline/eval/judge_result_answer/judge_result_toolcall/judge）"
    )
    parser.add_argument("input", nargs="?", default=None, help="输入 JSONL 文件（默认读 stdin）")
    parser.add_argument("-o", "--output", default=None, help="输出 CSV 文件（默认写 stdout）")
    args = parser.parse_args()

    # Input
    if args.input:
        with open(args.input) as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    # Header
    header = "query,keypoint,baseline,eval,judge_result_answer,judge_result_toolcall,judge"

    # Process
    rows = [header]
    errors = 0
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(process_line(line))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            errors += 1
            print(f"️  第 {i} 行解析失败，已跳过: {e}", file=sys.stderr)

    output_text = "\n".join(rows) + "\n"

    # Output
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_text)
        msg = f" 已导出 {len(rows) - 1} 条到 {args.output}"
        if errors:
            msg += f"（{errors} 条解析失败已跳过）"
        print(msg, file=sys.stderr)
    else:
        sys.stdout.write(output_text)


if __name__ == "__main__":
    main()
