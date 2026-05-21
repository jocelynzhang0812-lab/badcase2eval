#!/usr/bin/env python3
"""
上传后校验：检查 Platform Dataset 完整性，支持多种数据源对比。

用法:
    # 对比本地文件（CSV/JSONL/XLSX）
    python data-verify_upload.py --dataset <name> --file <path>

    # 对比[Internal Docs Platform] bitable（自动调 bitable_to_orbit.py 导出再比）
    python data-verify_upload.py --dataset <name> --bitable <url> [--field-map "问题:query"]

    # 对比 trace JSON（自动调 trace_to_orbit.py 导出再比）
    python data-verify_upload.py --dataset <name> --trace <path> [--turn 0]

    # 对比另一个 Platform dataset
    python data-verify_upload.py --dataset <name> --source-dataset <other_name>

    # 只检查 dataset 自身（无数据源对比）
    python data-verify_upload.py --dataset <name> [--expected-count 330]

校验项:
  始终执行: 条数、字段列表、空值统计、key field 重复检测
  有数据源时额外执行: 条数对比、key field 集合对比
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# ────────────────── Platform CLI helpers ──────────────────

def find_orbit_cli() -> str:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "Platform" / "Platform.mjs",
        Path.home() / ".kitty" / "skills" / "Platform" / "Platform.mjs",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return "Platform.mjs"


def fetch_dataset_items(dataset_name: str, orbit_cli: str) -> list[dict]:
    """分页获取 Platform Dataset 的所有 items。"""
    all_items = []
    page = 1
    while True:
        result = subprocess.run(
            ["node", orbit_cli, "datasets", "--items", dataset_name, "--page", str(page)],
            capture_output=True, text=True, env={**os.environ},
        )
        if result.returncode != 0:
            print(f" Platform CLI 报错: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        data = json.loads(result.stdout)
        items = data.get("items", [])
        total = data.get("total", 0)
        if not items:
            break
        all_items.extend(items)
        if total and len(all_items) >= total:
            break
        page += 1
    return all_items


# ────────────────── 数据源加载 ──────────────────

def load_from_file(path: str) -> list[dict]:
    """读取本地文件 (CSV/JSONL/XLSX)。"""
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".jsonl":
        rows = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    if suffix == ".csv":
        with open(p, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    if suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
        except ImportError:
            print(" 读取 Excel 需要 openpyxl: pip install openpyxl", file=sys.stderr)
            sys.exit(1)
        wb = openpyxl.load_workbook(p, read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h) for h in next(rows_iter)]
        return [
            dict(zip(headers, [str(v) if v is not None else "" for v in row]))
            for row in rows_iter
        ]

    print(f" 不支持的文件格式: {suffix}（支持 .csv, .jsonl, .xlsx）", file=sys.stderr)
    sys.exit(1)


def load_from_bitable(url: str, field_map: str | None = None) -> list[dict]:
    """调用 bitable_to_orbit.py 导出到临时 JSONL，再读取。"""
    scripts_dir = Path(__file__).resolve().parent
    bitable_script = scripts_dir / "data-bitable_to_orbit.py"
    if not bitable_script.exists():
        print(f" 找不到 {bitable_script}", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = [sys.executable, str(bitable_script), url, "-o", tmp_path]
        if field_map:
            cmd += ["--field-map", field_map]
        print("   从[Internal Docs Platform] bitable 拉数据...")
        result = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ})
        if result.returncode != 0:
            print(f" bitable_to_orbit.py 报错:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
        return load_from_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def load_from_trace(trace_path: str, turn: int = 0) -> list[dict]:
    """调用 trace_to_orbit.py 导出 dataset JSONL，再读取。"""
    scripts_dir = Path(__file__).resolve().parent
    trace_script = scripts_dir / "data-trace_to_orbit.py"
    if not trace_script.exists():
        print(f" 找不到 {trace_script}", file=sys.stderr)
        sys.exit(1)

    # trace_to_orbit.py 输出到 orbit_replay/<chat_id>/dataset.jsonl
    print(f"   从 trace 构造数据集 (turn={turn})...")
    result = subprocess.run(
        [sys.executable, str(trace_script), trace_path, "--turn", str(turn)],
        capture_output=True, text=True, env={**os.environ},
    )
    if result.returncode != 0:
        print(f" trace_to_orbit.py 报错:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    # 从 stdout 找到输出的 dataset.jsonl 路径
    output_path = None
    for line in result.stdout.splitlines():
        if "dataset.jsonl" in line:
            # 尝试提取路径
            for part in line.split():
                if "dataset.jsonl" in part:
                    candidate = Path(part)
                    if candidate.exists():
                        output_path = str(candidate)
                        break
    if not output_path:
        # fallback: 从 trace 文件名推断
        chat_id = Path(trace_path).stem
        candidate = Path("orbit_replay") / chat_id / "dataset.jsonl"
        if candidate.exists():
            output_path = str(candidate)

    if not output_path or not Path(output_path).exists():
        print(" trace_to_orbit.py 没有生成 dataset.jsonl", file=sys.stderr)
        print(f"  stdout: {result.stdout[:300]}", file=sys.stderr)
        sys.exit(1)

    return load_from_file(output_path)


def load_from_dataset(dataset_name: str, orbit_cli: str) -> list[dict]:
    """从另一个 Platform Dataset 拉取 items。"""
    print(f"   从 Platform Dataset '{dataset_name}' 拉数据...")
    items = fetch_dataset_items(dataset_name, orbit_cli)
    # 展平 input/metadata 为 flat dict
    rows = []
    for item in items:
        row = {}
        if isinstance(item.get("input"), dict):
            row.update(item["input"])
        if isinstance(item.get("metadata"), dict):
            row.update(item["metadata"])
        rows.append(row)
    return rows


# ────────────────── 字段提取 ──────────────────

def extract_values(items: list[dict], field: str) -> list[str]:
    """从 items 中提取指定字段。自动处理 Platform 的 input/metadata 嵌套。"""
    values = []
    for item in items:
        if "input" in item and isinstance(item["input"], dict):
            val = item["input"].get(field, item.get("metadata", {}).get(field, ""))
        else:
            val = item.get(field, "")
        values.append(str(val).strip() if val else "")
    return values


# ────────────────── 校验逻辑 ──────────────────

def verify(ds_items: list[dict], source_rows: list[dict] | None,
           key: str, expected_count: int | None) -> bool:
    """执行校验，返回 True = 全部通过。"""
    ds_count = len(ds_items)
    all_pass = True

    # --- Check 1: 条数 ---
    if source_rows is not None:
        src_count = len(source_rows)
        if ds_count == src_count:
            print(f" 条数一致: {ds_count}")
        else:
            print(f" 条数不一致: Dataset={ds_count}, 数据源={src_count}")
            all_pass = False
    elif expected_count is not None:
        if ds_count == expected_count:
            print(f" 条数符合预期: {ds_count}")
        else:
            print(f" 条数不符: Dataset={ds_count}, 预期={expected_count}")
            all_pass = False
    else:
        print(f" Dataset 条数: {ds_count}")

    # --- Check 2: key field 集合对比 ---
    ds_values = extract_values(ds_items, key)

    if source_rows is not None:
        # source_rows 是 flat dict，直接取字段
        src_values = [str(row.get(key, "")).strip() for row in source_rows]
        ds_set = set(ds_values)
        src_set = set(src_values)

        if not any(ds_values):
            print(f"️  Dataset 中字段 '{key}' 全为空")
            all_pass = False
        if not any(src_values):
            print(f"️  数据源中字段 '{key}' 全为空")
            all_pass = False

        only_ds = ds_set - src_set
        only_src = src_set - ds_set

        if not only_ds and not only_src:
            print(f" {key} 集合完全匹配（{len(ds_set & src_set)} 个唯一值）")
        else:
            all_pass = False
            print(f" {key} 集合不一致:")
            print(f"   共同: {len(ds_set & src_set)}")
            if only_ds:
                print(f"   仅 Dataset 有: {len(only_ds)}")
                for v in sorted(only_ds)[:3]:
                    print(f"     - {v[:80]}")
                if len(only_ds) > 3:
                    print(f"     ... 还有 {len(only_ds) - 3} 条")
            if only_src:
                print(f"   仅数据源有: {len(only_src)}")
                for v in sorted(only_src)[:3]:
                    print(f"     - {v[:80]}")
                if len(only_src) > 3:
                    print(f"     ... 还有 {len(only_src) - 3} 条")

    # --- Check 3: 重复检测 ---
    ds_dupes = ds_count - len(set(ds_values))
    if ds_dupes:
        print(f"️  Dataset 中 {key} 有 {ds_dupes} 条重复")
    else:
        print(f" {key} 无重复（{len(set(ds_values))} 个唯一值）")

    if source_rows is not None:
        src_values = [str(row.get(key, "")).strip() for row in source_rows]
        src_dupes = len(source_rows) - len(set(src_values))
        if src_dupes:
            print(f"️  数据源中 {key} 有 {src_dupes} 条重复")

    # --- Check 4: 字段 & 空值 ---
    if ds_items:
        sample = ds_items[0]
        input_fields = list(sample.get("input", {}).keys()) if isinstance(sample.get("input"), dict) else []
        meta_fields = list(sample.get("metadata", {}).keys()) if isinstance(sample.get("metadata"), dict) else []
        print(f"\n 字段: Input={input_fields}, Metadata={meta_fields}")

        empty_stats = {}
        for field in input_fields + meta_fields:
            vals = extract_values(ds_items, field)
            empty_count = sum(1 for v in vals if not v)
            if empty_count > 0:
                empty_stats[field] = empty_count

        if empty_stats:
            print("️  空值字段:")
            for f, c in empty_stats.items():
                print(f"   {f}: {c}/{ds_count} 条为空")
        else:
            print(" 所有字段无空值")

    return all_pass


# ────────────────── Main ──────────────────

def main():
    parser = argparse.ArgumentParser(
        description="上传后校验：检查 Platform Dataset 完整性，支持多种数据源对比",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
数据源（四选一，都不传则只检查 dataset 自身）:
  --file <path>              本地文件 (CSV/JSONL/XLSX)
  --bitable <url>            [Internal Docs Platform]多维表格 URL
  --trace <path>             trace JSON 文件
  --source-dataset <name>    另一个 Platform dataset
        """,
    )
    parser.add_argument("--dataset", required=True, help="要校验的 Platform Dataset 名称")
    parser.add_argument("--key-field", default="query", help="主键字段（默认 query）")
    parser.add_argument("--expected-count", type=int, default=None, help="预期条数")
    parser.add_argument("--Platform-cli", default=None, help="Platform.mjs 路径")

    # 数据源（四选一）
    src = parser.add_argument_group("数据源")
    src.add_argument("--file", default=None, help="本地文件 (.csv/.jsonl/.xlsx)")
    src.add_argument("--bitable", default=None, help="[Internal Docs Platform]多维表格 URL")
    src.add_argument("--trace", default=None, help="trace JSON 文件路径")
    src.add_argument("--source-dataset", default=None, help="另一个 Platform Dataset 名称")

    # 数据源特定参数
    parser.add_argument("--field-map", default=None, help="bitable 字段映射（如 '问题:query,标准:rubric'）")
    parser.add_argument("--turn", type=int, default=0, help="trace 的 turn 索引（默认 0）")

    args = parser.parse_args()
    orbit_cli = args.orbit_cli or find_orbit_cli()

    # 检查数据源互斥
    sources = [s for s in [args.file, args.bitable, args.trace, args.source_dataset] if s]
    if len(sources) > 1:
        print(" --file / --bitable / --trace / --source-dataset 只能选一个", file=sys.stderr)
        sys.exit(1)

    # 1. 获取 Platform dataset items
    print(f" 拉取 Platform Dataset: {args.dataset} ...")
    ds_items = fetch_dataset_items(args.dataset, orbit_cli)

    # 2. 加载数据源
    source_rows = None
    if args.file:
        print(f" 数据源: 本地文件 {args.file}")
        source_rows = load_from_file(args.file)
    elif args.bitable:
        print(f" 数据源: [Internal Docs Platform] bitable {args.bitable}")
        source_rows = load_from_bitable(args.bitable, args.field_map)
    elif args.trace:
        print(f" 数据源: trace {args.trace}")
        source_rows = load_from_trace(args.trace, args.turn)
    elif args.source_dataset:
        print(f" 数据源: Platform Dataset {args.source_dataset}")
        source_rows = load_from_dataset(args.source_dataset, orbit_cli)
    else:
        print(" 数据源: 无（只检查 dataset 自身）")

    # 3. 校验
    print()
    print("=" * 50)
    print(" 校验报告")
    print("=" * 50)

    all_pass = verify(ds_items, source_rows, args.key_field, args.expected_count)

    print()
    print(" 校验通过！" if all_pass else "️  存在差异，请检查上述问题。")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
