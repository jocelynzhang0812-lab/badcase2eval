#!/usr/bin/env python3
"""data-sanitize_pii.py  扫描并脱敏线上数据中的个人隐私信息 (PII)

支持检测：
  - 身份证号（18 位 / 15 位）
  - 手机号（中国大陆 11 位）
  - 邮箱地址
  - 银行卡号（16-19 位）
  - API Key / Secret Key / Token（sk-xxx, AKIA xxx, Bearer xxx 等）
  - 密码字段（password=xxx, secret=xxx 等键值对）
  - IPv4 地址（排除 127.0.0.1 等常见内网地址）

用法:
    # 扫描本地 JSONL 文件，仅报告
    python scripts/data-sanitize_pii.py scan --file data.jsonl

    # 扫描并脱敏，输出到新文件
    python scripts/data-sanitize_pii.py redact --file data.jsonl --output data_clean.jsonl

    # 扫描 Platform 数据集
    python scripts/data-sanitize_pii.py scan --datasets "ds1,ds2"

    # 脱敏 Platform 数据集 (先 dry-run)
    python scripts/data-sanitize_pii.py redact --datasets "ds1,ds2" --dry-run

    # 确认后正式写回 Platform
    python scripts/data-sanitize_pii.py redact --datasets "ds1,ds2"

    # 保存扫描报告
    python scripts/data-sanitize_pii.py scan --file data.jsonl --output report.json
"""

import os
import re
import csv
import json
import copy
import argparse
import urllib.parse
from typing import Any, Dict, List, Tuple

try:
    import requests
except ImportError:
    requests = None  # Platform 功能不可用，本地文件模式仍可用


# ============================================================================
# PII 检测规则
# ============================================================================

# 身份证号: 18 位（最后一位可能是 X）或老式 15 位
_ID_CARD_18 = re.compile(
    r'(?<!\d)'
    r'[1-9]\d{5}'                              # 地区码
    r'(?:19|20)\d{2}'                           # 出生年
    r'(?:0[1-9]|1[0-2])'                        # 月
    r'(?:0[1-9]|[12]\d|3[01])'                  # 日
    r'\d{3}[\dXx]'                              # 顺序码 + 校验码
    r'(?!\d)'
)
_ID_CARD_15 = re.compile(
    r'(?<!\d)'
    r'[1-9]\d{5}'
    r'\d{2}'                                    # 2 位年
    r'(?:0[1-9]|1[0-2])'
    r'(?:0[1-9]|[12]\d|3[01])'
    r'\d{3}'
    r'(?!\d)'
)

# 手机号: 1 开头，第二位 3-9，共 11 位
_PHONE = re.compile(
    r'(?<!\d)1[3-9]\d{9}(?!\d)'
)

# 邮箱
_EMAIL = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
)

# 银行卡号: 16-19 位纯数字（排除身份证号场景，要求前后无字母数字）
_BANK_CARD = re.compile(
    r'(?<!\d)(?:62\d{14,17}|4\d{15,18}|5[1-5]\d{14,17}|3[47]\d{13,16})'
    r'(?!\d)'
)

# API Key / Secret Key / Token 模式
_API_KEY_PATTERNS = [
    # OpenAI-style: sk-xxx (至少 20 字符)
    re.compile(r'sk-[a-zA-Z0-9_\-]{20,}'),
    # AWS Access Key: AKIA + 16 chars
    re.compile(r'AKIA[0-9A-Z]{16}'),
    # Generic secret/token in quotes or after =
    re.compile(
        r'(?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|auth[_\-]?token'
        r'|private[_\-]?key|client[_\-]?secret|app[_\-]?secret)'
        r'\s*[:=]\s*["\']?([a-zA-Z0-9_\-./+]{16,})["\']?',
        re.IGNORECASE,
    ),
    # Bearer token
    re.compile(r'Bearer\s+[a-zA-Z0-9_\-./+]{20,}', re.IGNORECASE),
    # GitHub PAT: ghp_ / gho_ / ghs_ / ghr_
    re.compile(r'(?:ghp|gho|ghs|ghr)_[a-zA-Z0-9_]{36,}'),
    # AuthGateway token (长随机串 with common prefixes)
    re.compile(r'(?:mgt|pat|token)[_\-][a-zA-Z0-9_\-]{20,}', re.IGNORECASE),
]

# 密码字段: password=xxx, passwd: xxx 等
_PASSWORD_KV = re.compile(
    r'(?:password|passwd|pwd|密码)\s*[:=]\s*["\']?(\S{4,})["\']?',
    re.IGNORECASE,
)

# IPv4（排除 localhost 和常见内网保留地址段的完全匹配）
_IPV4 = re.compile(
    r'(?<!\d)(?!127\.0\.0\.1)(?!0\.0\.0\.0)(?!255\.255\.255\.255)'
    r'(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
    r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)'
    r'(?!\d)'
)

# 所有规则汇总: (名称, 正则, 脱敏函数)
PII_RULES: List[Tuple[str, re.Pattern, str]] = [
    ("身份证号",    _ID_CARD_18, "id_card"),
    ("身份证号15",  _ID_CARD_15, "id_card"),
    ("手机号",      _PHONE,      "phone"),
    ("邮箱",        _EMAIL,      "email"),
    ("银行卡号",    _BANK_CARD,  "bank_card"),
    ("密码字段",    _PASSWORD_KV, "password_kv"),
    ("IPv4地址",    _IPV4,       "ipv4"),
]

# API key 规则单独处理（多个 pattern）
for i, pat in enumerate(_API_KEY_PATTERNS):
    PII_RULES.append((f"API_Key_{i}", pat, "api_key"))


# ============================================================================
# 脱敏函数
# ============================================================================

def _mask(s: str, keep_prefix: int = 3, keep_suffix: int = 4, mask_char: str = "*") -> str:
    """通用遮掩：保留前 N 后 M 位，中间用 * 填充。"""
    if len(s) <= keep_prefix + keep_suffix:
        return mask_char * len(s)
    return s[:keep_prefix] + mask_char * (len(s) - keep_prefix - keep_suffix) + s[-keep_suffix:]


def redact_match(match: re.Match, rule_type: str) -> str:
    """根据规则类型对匹配内容进行脱敏。"""
    text = match.group(0)

    if rule_type == "id_card":
        # 保留前 3 后 4: 110***********1234
        return _mask(text, 3, 4)

    if rule_type == "phone":
        # 保留前 3 后 4: 138****1234
        return _mask(text, 3, 4)

    if rule_type == "email":
        # user@domain → u***@domain
        parts = text.split("@", 1)
        if len(parts) == 2:
            user, domain = parts
            masked_user = user[0] + "***" if len(user) > 1 else "***"
            return f"{masked_user}@{domain}"
        return "***@***.***"

    if rule_type == "bank_card":
        # 保留前 4 后 4
        return _mask(text, 4, 4)

    if rule_type == "api_key":
        # 保留前 6 后 4（或全遮）
        return _mask(text, 6, 4)

    if rule_type == "password_kv":
        # 替换整个值部分
        kv_match = _PASSWORD_KV.match(text)
        if kv_match:
            val = kv_match.group(1)
            return text.replace(val, "***REDACTED***")
        return text

    if rule_type == "ipv4":
        # 保留前段: 10.xx.*.*
        parts = text.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.*.*"
        return "*.*.*.* "

    return "***REDACTED***"


# ============================================================================
# 扫描与脱敏核心
# ============================================================================

def scan_text(text: str) -> List[Dict[str, Any]]:
    """扫描文本，返回所有 PII 命中。"""
    hits = []
    for rule_name, pattern, rule_type in PII_RULES:
        for m in pattern.finditer(text):
            snippet = text[max(0, m.start() - 20):m.end() + 20]
            hits.append({
                "type": rule_name,
                "match": m.group(0),
                "start": m.start(),
                "end": m.end(),
                "snippet": snippet.replace("\n", "\\n"),
            })
    return hits


def redact_text(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """对文本进行脱敏，返回 (新文本, 替换记录)。"""
    changes = []
    # 收集所有匹配，按位置倒序替换以避免偏移
    all_matches = []
    for rule_name, pattern, rule_type in PII_RULES:
        for m in pattern.finditer(text):
            all_matches.append((m.start(), m.end(), m, rule_name, rule_type))

    if not all_matches:
        return text, changes

    # 按 start 降序排列，从后往前替换
    all_matches.sort(key=lambda x: x[0], reverse=True)

    # 去重重叠区间：保留最先匹配到的（即 start 最大的先处理，但要去除完全重叠的）
    used_ranges = []
    filtered = []
    for start, end, m, rule_name, rule_type in all_matches:
        overlap = False
        for us, ue in used_ranges:
            if start < ue and end > us:
                overlap = True
                break
        if not overlap:
            filtered.append((start, end, m, rule_name, rule_type))
            used_ranges.append((start, end))

    new_text = text
    for start, end, m, rule_name, rule_type in filtered:
        original = m.group(0)
        replacement = redact_match(m, rule_type)
        new_text = new_text[:start] + replacement + new_text[end:]
        changes.append({
            "type": rule_name,
            "original": original,
            "replacement": replacement,
        })

    return new_text, changes


def extract_all_strings(obj: Any, path: str = "root") -> List[Tuple[str, str]]:
    """递归提取对象中所有字符串值及其路径。"""
    strings = []
    if isinstance(obj, str):
        strings.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            strings.extend(extract_all_strings(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            strings.extend(extract_all_strings(v, f"{path}[{i}]"))
    return strings


def scan_obj(obj: Any) -> List[Dict[str, Any]]:
    """扫描整个对象中的 PII。"""
    results = []
    for path, text in extract_all_strings(obj):
        hits = scan_text(text)
        for h in hits:
            h["path"] = path
        results.extend(hits)
    return results


def redact_obj(obj: Any, path: str = "root") -> Tuple[Any, List[Dict[str, Any]]]:
    """递归脱敏对象中所有字符串值。"""
    all_changes = []

    if isinstance(obj, str):
        new_text, changes = redact_text(obj)
        for c in changes:
            c["path"] = path
        return new_text, changes

    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            new_v, changes = redact_obj(v, f"{path}.{k}")
            new_dict[k] = new_v
            all_changes.extend(changes)
        return new_dict, all_changes

    if isinstance(obj, list):
        new_list = []
        for i, v in enumerate(obj):
            new_v, changes = redact_obj(v, f"{path}[{i}]")
            new_list.append(new_v)
            all_changes.extend(changes)
        return new_list, all_changes

    return obj, all_changes


# ============================================================================
# 文件级操作
# ============================================================================

def process_file_scan(filepath: str) -> Dict[str, Any]:
    """扫描本地文件 (JSONL/CSV/JSON)，返回报告。"""
    ext = os.path.splitext(filepath)[1].lower()
    all_hits = []
    total_records = 0

    if ext in (".jsonl", ".ndjson"):
        with open(filepath, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total_records += 1
                hits = scan_obj(obj)
                for h in hits:
                    h["line"] = i
                all_hits.extend(hits)

    elif ext == ".json":
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for i, obj in enumerate(data):
                total_records += 1
                hits = scan_obj(obj)
                for h in hits:
                    h["line"] = i + 1
                all_hits.extend(hits)
        else:
            total_records = 1
            all_hits = scan_obj(data)

    elif ext == ".csv":
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, 1):
                total_records += 1
                hits = scan_obj(dict(row))
                for h in hits:
                    h["line"] = i
                all_hits.extend(hits)
    else:
        # 当作纯文本
        with open(filepath, encoding="utf-8") as f:
            text = f.read()
        total_records = 1
        all_hits = scan_text(text)

    return {
        "file": filepath,
        "total_records": total_records,
        "hit_count": len(all_hits),
        "hits": all_hits,
        "hit_types": sorted(set(h["type"] for h in all_hits)),
    }


def process_file_redact(filepath: str, output_path: str) -> Dict[str, Any]:
    """脱敏本地文件并输出。"""
    ext = os.path.splitext(filepath)[1].lower()
    all_changes = []
    total_records = 0

    if ext in (".jsonl", ".ndjson"):
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()

        out_lines = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                out_lines.append(line)
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                out_lines.append(line)
                continue
            total_records += 1
            new_obj, changes = redact_obj(obj)
            for c in changes:
                c["line"] = i
            all_changes.extend(changes)
            out_lines.append(json.dumps(new_obj, ensure_ascii=False) + "\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(out_lines)

    elif ext == ".json":
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            new_data = []
            for i, obj in enumerate(data):
                total_records += 1
                new_obj, changes = redact_obj(obj)
                for c in changes:
                    c["line"] = i + 1
                all_changes.extend(changes)
                new_data.append(new_obj)
        else:
            total_records = 1
            new_data, all_changes = redact_obj(data)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)

    elif ext == ".csv":
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)

        new_rows = []
        for i, row in enumerate(rows, 1):
            total_records += 1
            new_row, changes = redact_obj(dict(row))
            for c in changes:
                c["line"] = i
            all_changes.extend(changes)
            new_rows.append(new_row)

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(new_rows)

    else:
        with open(filepath, encoding="utf-8") as f:
            text = f.read()
        total_records = 1
        new_text, all_changes = redact_text(text)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(new_text)

    return {
        "file": filepath,
        "output": output_path,
        "total_records": total_records,
        "redaction_count": len(all_changes),
        "changes": all_changes,
        "change_types": sorted(set(c["type"] for c in all_changes)),
    }


# ============================================================================
# Platform 数据集操作
# ============================================================================

def get_auth_headers() -> Dict[str, str]:
    token = os.environ.get("AuthGateway_ACCESS_TOKEN")
    if not token:
        raise ValueError("AuthGateway_ACCESS_TOKEN environment variable not set")
    return {"X-AuthGateway-Access-Token": token}


def fetch_all_items(
    dataset_name: str, base_url: str, headers: Dict[str, str]
) -> List[Dict[str, Any]]:
    all_items = []
    page = 1
    encoded = urllib.parse.quote(dataset_name, safe="")
    while True:
        try:
            r = requests.get(
                f"{base_url}/api/datasets/{encoded}/items",
                headers=headers,
                params={"page": page, "limit": 50},
                timeout=60,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                break
            all_items.extend(items)
            if len(items) < 50:
                break
            page += 1
        except Exception as e:
            print(f"  Error fetching {dataset_name} page {page}: {e}")
            break
    return all_items


def patch_item(
    dataset_name: str, item_id: str,
    new_input: Any, new_metadata: Any,
    base_url: str, headers: Dict[str, str],
) -> bool:
    encoded = urllib.parse.quote(dataset_name, safe="")
    body = {}
    if new_input is not None:
        body["input"] = new_input
    if new_metadata is not None:
        body["metadata"] = new_metadata
    try:
        r = requests.patch(
            f"{base_url}/api/datasets/{encoded}/items/{item_id}",
            headers={**headers, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  Error patching item {item_id}: {e}")
        return False


def scan_orbit_dataset(
    dataset_name: str, base_url: str, headers: Dict[str, str]
) -> Dict[str, Any]:
    print(f"Scanning {dataset_name} ...", flush=True)
    items = fetch_all_items(dataset_name, base_url, headers)
    print(f"  Fetched {len(items)} items", flush=True)

    all_hits = []
    for item in items:
        item_id = item.get("id", "unknown")
        hits = scan_obj(item)
        for h in hits:
            h["item_id"] = item_id
        all_hits.extend(hits)

    return {
        "dataset_name": dataset_name,
        "total_items": len(items),
        "hit_count": len(all_hits),
        "hits": all_hits,
        "hit_types": sorted(set(h["type"] for h in all_hits)),
    }


def redact_orbit_dataset(
    dataset_name: str, base_url: str, headers: Dict[str, str],
    dry_run: bool = True,
) -> Dict[str, Any]:
    print(f"Processing {dataset_name} ...", flush=True)
    items = fetch_all_items(dataset_name, base_url, headers)
    print(f"  Fetched {len(items)} items", flush=True)

    modified = []
    total_redactions = 0

    for item in items:
        item_id = item.get("id", "unknown")
        original_input = item.get("input")
        original_metadata = item.get("metadata")

        new_input, input_changes = redact_obj(copy.deepcopy(original_input))
        new_meta, meta_changes = redact_obj(copy.deepcopy(original_metadata))

        all_changes = input_changes + meta_changes
        if not all_changes:
            continue

        total_redactions += len(all_changes)
        entry = {
            "item_id": item_id,
            "redaction_count": len(all_changes),
            "changes": all_changes,
            "patched": False,
        }

        if not dry_run:
            ok = patch_item(dataset_name, item_id, new_input, new_meta, base_url, headers)
            entry["patched"] = ok
            status = "" if ok else ""
            print(f"  {status} Patched item {item_id} ({len(all_changes)} redactions)")
        else:
            print(f"  [dry-run] Item {item_id}: {len(all_changes)} PII found")

        modified.append(entry)

    return {
        "dataset_name": dataset_name,
        "total_items": len(items),
        "modified_items": len(modified),
        "total_redactions": total_redactions,
        "details": modified,
    }


# ============================================================================
# 报告输出
# ============================================================================

def print_scan_report(results: List[Dict[str, Any]], source: str = "file"):
    """打印扫描报告。"""
    total_records = sum(r.get("total_records", r.get("total_items", 0)) for r in results)
    total_hits = sum(r["hit_count"] for r in results)
    all_types = set()
    for r in results:
        all_types.update(r.get("hit_types", []))

    print()
    print("=" * 80)
    print("PII 扫描报告")
    print("=" * 80)
    print(f"扫描来源:    {source}")
    print(f"总记录数:    {total_records}")
    print(f"命中总数:    {total_hits}")
    print(f"命中类型:    {', '.join(sorted(all_types)) if all_types else '无'}")
    print()

    if total_hits == 0:
        print(" 未检测到 PII，数据可安全使用。")
        return

    # 按类型统计
    type_counts: Dict[str, int] = {}
    for r in results:
        for h in r.get("hits", []):
            t = h["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

    print("-" * 60)
    print(f"{'PII 类型':<20} {'命中次数':>10}")
    print("-" * 60)
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"{t:<20} {c:>10}")
    print("-" * 60)
    print()

    # 详细命中（每种类型最多显示 5 条）
    shown: Dict[str, int] = {}
    for r in results:
        for h in r.get("hits", []):
            t = h["type"]
            shown[t] = shown.get(t, 0)
            if shown[t] >= 5:
                continue
            shown[t] += 1
            loc = ""
            if "line" in h:
                loc = f"行 {h['line']}"
            if "item_id" in h:
                loc = f"Item {h['item_id']}"
            if "path" in h:
                loc += f" @ {h['path']}"
            snippet = h.get("snippet", h.get("match", ""))
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            print(f"  [{t}] {loc}")
            print(f"    {snippet}")
            print()


def print_redact_report(results: List[Dict[str, Any]], dry_run: bool):
    """打印脱敏报告。"""
    mode = "DRY-RUN" if dry_run else "已执行"
    total = sum(r.get("redaction_count", r.get("total_redactions", 0)) for r in results)

    print()
    print("=" * 80)
    print(f"PII 脱敏报告  ({mode})")
    print("=" * 80)
    print(f"总脱敏数: {total}")
    print()

    for r in results:
        name = r.get("file", r.get("dataset_name", "unknown"))
        count = r.get("redaction_count", r.get("total_redactions", 0))
        print(f"  {name}: {count} 处脱敏")
        changes = r.get("changes", [])
        if not changes and "details" in r:
            for d in r["details"][:5]:
                changes.extend(d.get("changes", []))
        for c in changes[:10]:
            orig = c.get("original", "")
            repl = c.get("replacement", "")
            if len(orig) > 40:
                orig = orig[:37] + "..."
            if len(repl) > 40:
                repl = repl[:37] + "..."
            print(f"    [{c['type']}] {orig} → {repl}")
        if count > 10:
            print(f"    ... 共 {count} 处")
        print()


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="扫描并脱敏线上数据中的个人隐私信息 (PII)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="action", required=True)

    # scan 子命令
    scan_p = sub.add_parser("scan", help="扫描 PII，仅报告不修改")
    scan_p.add_argument("--file", type=str, help="本地文件路径 (JSONL/CSV/JSON)")
    scan_p.add_argument("--datasets", type=str, help="Platform 数据集名（逗号分隔）")
    scan_p.add_argument("--output", type=str, help="将报告保存为 JSON 文件")
    scan_p.add_argument("--base-url", default="https://platform.internal.ai.com")

    # redact 子命令
    red_p = sub.add_parser("redact", help="扫描并脱敏 PII")
    red_p.add_argument("--file", type=str, help="本地文件路径")
    red_p.add_argument("--output", type=str, help="脱敏后输出路径（本地文件模式必填）")
    red_p.add_argument("--datasets", type=str, help="Platform 数据集名（逗号分隔）")
    red_p.add_argument("--dry-run", action="store_true", help="仅显示将脱敏的内容")
    red_p.add_argument("--base-url", default="https://platform.internal.ai.com")

    args = parser.parse_args()

    if args.action == "scan":
        results = []
        if args.file:
            results.append(process_file_scan(args.file))
            print_scan_report(results, source=args.file)
        elif args.datasets:
            headers = get_auth_headers()
            names = [d.strip() for d in args.datasets.split(",")]
            for name in names:
                results.append(scan_orbit_dataset(name, args.base_url, headers))
            print_scan_report(results, source="Platform")
        else:
            parser.error("需指定 --file 或 --datasets")

        if args.output:
            # 序列化前清理 set
            for r in results:
                if "hit_types" in r:
                    r["hit_types"] = list(r["hit_types"])
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n报告已保存到 {args.output}")

    elif args.action == "redact":
        results = []
        if args.file:
            if not args.output:
                # 默认输出文件名
                base, ext = os.path.splitext(args.file)
                args.output = f"{base}_clean{ext}"
                print(f"输出路径未指定，将写入: {args.output}")
            result = process_file_redact(args.file, args.output)
            results.append(result)
            print_redact_report(results, dry_run=False)
        elif args.datasets:
            headers = get_auth_headers()
            names = [d.strip() for d in args.datasets.split(",")]
            for name in names:
                result = redact_orbit_dataset(
                    name, args.base_url, headers, dry_run=args.dry_run
                )
                results.append(result)
            print_redact_report(results, dry_run=args.dry_run)
        else:
            parser.error("需指定 --file 或 --datasets")

        if args.action == "redact" and hasattr(args, "output") and args.output and args.datasets:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"脱敏日志已保存到 {args.output}")


if __name__ == "__main__":
    main()
