#!/usr/bin/env python3
"""csv_to_orbit.py  将 BMK CSV/Excel 转为 Platform JSONL 格式

用法:
    python scripts/csv_to_orbit.py input.csv [output.jsonl]
    python scripts/csv_to_orbit.py input.xlsx [output.jsonl]
"""

import csv
import json
import sys
from pathlib import Path

# 字段映射：CSV 列名 → Platform 字段名
FIELD_MAP = {
    # query 相关（优先级从高到低）
    "query": "query",
    "问题": "query",
    "user_query": "query",
    # rubric 相关
    "rubric": "rubric",
    "打分点": "rubric",
    "ground_truth": "rubric",
    "评判标准": "rubric",
    # metadata
    "scenario": "scenario",
    "场景": "scenario",
    "difficulty": "difficulty",
    "难度": "difficulty",
}


def normalize_field(name: str) -> str:
    """将中文/变体列名映射为标准 Platform 字段名"""
    return FIELD_MAP.get(name.strip(), name.strip())


def read_rows(input_path: str) -> list[dict]:
    """读取 CSV 或 Excel 文件，返回 list of dict"""
    suffix = Path(input_path).suffix.lower()

    if suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
        except ImportError:
            print(" 读取 Excel 需要 openpyxl: pip install openpyxl")
            sys.exit(1)
        wb = openpyxl.load_workbook(input_path, read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h) if h is not None else "" for h in next(rows_iter)]
        rows = []
        for row in rows_iter:
            rows.append({
                h: str(v) if v is not None else ""
                for h, v in zip(headers, row)
                if h  # skip empty headers
            })
        wb.close()
        return rows

    # Default: CSV
    with open(input_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def convert(input_path: str, output_jsonl: str):
    rows = read_rows(input_path)

    if not rows:
        print(" 文件为空")
        return

    records = []
    for row in rows:
        record = {}
        for k, v in row.items():
            norm_key = normalize_field(k)
            if v and v.strip():
                record[norm_key] = v.strip()
        if "query" not in record:
            print(f"️  跳过缺少 query 的行: {row}")
            continue
        records.append(record)

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f" 转换完成: {len(records)} 条 → {output_jsonl}")
    print(f"   字段: {list(records[0].keys()) if records else '无'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/csv_to_orbit.py input.csv|input.xlsx [output.jsonl]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(input_path).with_suffix(".jsonl")
    )
    convert(input_path, output_path)
