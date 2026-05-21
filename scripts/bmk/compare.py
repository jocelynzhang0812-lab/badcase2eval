#!/usr/bin/env python3
"""
对比两组 batch_chatty 输出目录的评测指标。

用法:
    python bmk/compare.py bmk/search_full_no_hook bmk/search_full_with_hook
    python bmk/compare.py bmk/search_full_no_hook bmk/search_full_with_hook --label-a "主分支(无hook)" --label-b "开发分支(有hook)"
    python bmk/compare.py bmk/A bmk/B --judge judge/result/xxx.xlsx --label-a A --label-b B
"""

import argparse
import json
import os
import re
import sys


# PUA Unicode 定界符（新引用格式）
_PUA_START = "\uE3A0"
_PUA_END = "\uE3A8"
_PUA_DELIM_TOOL = "\uE3A1"  # 工具结果 ref 分隔符
_PUA_DELIM_FILE = "\uE3A2"  # 文件路径/URL 分隔符
_PUA_DELIM_TOOLRESULT = "\uE3A3"  # 工具调用结果分隔符
_PUA_DELIMS = f"[{_PUA_DELIM_TOOL}{_PUA_DELIM_FILE}{_PUA_DELIM_TOOLRESULT}]"

# 旧格式: [^N^]
_RE_LEGACY_CITE = re.compile(r"\[\^\d+\^\]")
# 新格式: 匹配 Start...End 块，捕获完整内容
_RE_PUA_CITE = re.compile(f"{_PUA_START}(cite|file|image)(.*?){_PUA_END}")
# 新格式 article 卡片
_RE_PUA_ARTICLE = re.compile(f"{_PUA_START}article(.*?){_PUA_END}")


def _count_refs_in_block(block_body: str) -> int:
    """统计一个 PUA 引用块内的 ref 数量（按分隔符拆分）。"""
    refs = re.split(_PUA_DELIMS, block_body)
    return sum(1 for r in refs if r.strip())


def count_citations(text: str) -> dict:
    """
    统计引用数量，兼容新旧格式。
    返回 dict:
      legacy_refs: 旧格式 [^N^] 引用数
      pua_refs: 新格式 inline ref 总数
      pua_blocks: 新格式引用块数（每个 Start-End 对算 1 块）
      article_refs: article 卡片包含的 ref 数
      article_blocks: article 卡片块数
      unpaired_starts: 有 Start 无 End 的残缺块数
    """
    # 旧格式
    legacy_refs = len(_RE_LEGACY_CITE.findall(text))

    # 新格式 cite/file/image
    pua_refs = 0
    pua_blocks = 0
    for m in _RE_PUA_CITE.finditer(text):
        body = m.group(2)
        pua_refs += _count_refs_in_block(body)
        pua_blocks += 1

    # article 卡片
    article_refs = 0
    article_blocks = 0
    for m in _RE_PUA_ARTICLE.finditer(text):
        body = m.group(1)
        article_refs += _count_refs_in_block(body)
        article_blocks += 1

    # PUA 配对完整性：统计 Start 数量 vs 完整配对数量
    total_starts = text.count(_PUA_START)
    total_paired = pua_blocks + article_blocks
    unpaired_starts = total_starts - total_paired

    return {
        "legacy_refs": legacy_refs,
        "pua_refs": pua_refs,
        "pua_blocks": pua_blocks,
        "article_refs": article_refs,
        "article_blocks": article_blocks,
        "unpaired_starts": unpaired_starts,
    }


def analyze_group(dir_path: str) -> dict:
    files = sorted(
        [f for f in os.listdir(dir_path) if f.endswith(".json")],
        key=lambda x: int(re.sub(r"\D", "", x) or 0),
    )
    stats = {
        "total": 0,
        "ok": 0,
        "fail": 0,
        # MODEL BEHAVIOR
        "total_tokens": 0,
        "total_prompt": 0,
        "total_completion": 0,
        "total_reply_len": 0,
        "total_tool_calls": 0,
        "total_search_queries": 0,
        "total_search_calls": 0,
        "samples_with_search": 0,
        # SANITY CHECK - citations
        "legacy_refs": 0,
        "pua_refs": 0,
        "pua_blocks": 0,
        "total_citations": 0,  # legacy + pua
        "has_citations": 0,
        "article_refs": 0,
        "article_blocks": 0,
        "has_articles": 0,
        "unpaired_starts": 0,
        "samples_with_unpaired": 0,
        # search-only subset
        "search_citations": 0,
        "search_has_citations": 0,
        "search_articles": 0,
        "search_has_articles": 0,
        "search_reply_len": 0,
        "fail_indices": [],
    }

    for fname in files:
        fp = os.path.join(dir_path, fname)
        with open(fp) as f:
            data = json.load(f)

        stats["total"] += 1
        idx = data.get("index", fname)

        if data.get("error"):
            stats["fail"] += 1
            stats["fail_indices"].append(idx)
            continue

        stats["ok"] += 1
        events = data.get("output", [])
        model_ends = [e for e in events if e.get("type") == "model_end"]
        tool_ends = [e for e in events if e.get("type") == "tool_end"]

        # tokens
        for me in model_ends:
            u = me.get("usage") or {}
            stats["total_tokens"] += u.get("total_tokens", 0)
            stats["total_prompt"] += u.get("prompt_tokens", 0)
            stats["total_completion"] += u.get("completion_tokens", 0)

        # tool calls
        stats["total_tool_calls"] += len(tool_ends)

        # search query 数量
        sample_has_search = False
        for me in model_ends:
            for tc in me.get("message", {}).get("tool_calls", []):
                func = tc.get("function", {})
                if func.get("name") == "web_search":
                    stats["total_search_calls"] += 1
                    sample_has_search = True
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                        queries = args.get("queries", [])
                        stats["total_search_queries"] += len(queries)
                    except (json.JSONDecodeError, TypeError):
                        stats["total_search_queries"] += 1

        if sample_has_search:
            stats["samples_with_search"] += 1

        # 最终回复
        final_text = ""
        for me in model_ends:
            if me.get("finish_reason") == "stop":
                for c in me.get("message", {}).get("contents", []):
                    if c.get("text"):
                        final_text = c["text"]

        cites = count_citations(final_text)
        cite_total = cites["legacy_refs"] + cites["pua_refs"]
        stats["legacy_refs"] += cites["legacy_refs"]
        stats["pua_refs"] += cites["pua_refs"]
        stats["pua_blocks"] += cites["pua_blocks"]
        stats["total_citations"] += cite_total
        if cite_total:
            stats["has_citations"] += 1
        stats["article_refs"] += cites["article_refs"]
        stats["article_blocks"] += cites["article_blocks"]
        if cites["article_blocks"]:
            stats["has_articles"] += 1
        stats["unpaired_starts"] += cites["unpaired_starts"]
        if cites["unpaired_starts"] > 0:
            stats["samples_with_unpaired"] += 1
        stats["total_reply_len"] += len(final_text)

        if sample_has_search:
            stats["search_citations"] += cite_total
            if cite_total:
                stats["search_has_citations"] += 1
            stats["search_articles"] += cites["article_refs"]
            if cites["article_blocks"]:
                stats["search_has_articles"] += 1
            stats["search_reply_len"] += len(final_text)

    return stats


def print_comparison(a: dict, b: dict, label_a: str, label_b: str, judge: dict | None = None):
    ok_a, ok_b = a["ok"], b["ok"]
    if ok_a == 0 or ok_b == 0:
        print("ERROR: 至少一组没有成功的样本", file=sys.stderr)
        return

    def avg(total, n):
        return total / n if n else 0

    def pct_diff(va, vb):
        if va == 0:
            return "N/A"
        diff = (vb - va) / va * 100
        sign = "+" if diff >= 0 else ""
        return f"{sign}{diff:.1f}%"

    w0, w1, w2, w3 = 28, max(len(label_a), 15), max(len(label_b), 15), 10
    header = f"{'':>{w0}} | {label_a:>{w1}} | {label_b:>{w2}} | {'diff':>{w3}}"
    sep = f"{'':->{ w0}}-+-{'':->{ w1}}-+-{'':->{ w2}}-+-{'':->{ w3}}"

    def print_section(title, rows):
        print(f"\n{'=' * 3} {title} {'=' * (w0 + w1 + w2 + w3 - len(title) + 3)}")
        print(header)
        print(sep)
        for name, va, vb, diff in rows:
            print(f"{name:>{w0}} | {va:>{w1}} | {vb:>{w2}} | {diff:>{w3}}")

    # ── BENCHMARK SCORE ──
    if judge:
        score_rows = [
            ("avg_score",
             f"{judge['a_score']:.4f}", f"{judge['b_score']:.4f}",
             pct_diff(judge['a_score'], judge['b_score'])),
            ("score = 1",
             f"{judge['a_1']}", f"{judge['b_1']}", ""),
            ("score = 0.5",
             f"{judge['a_05']}", f"{judge['b_05']}", ""),
            ("score = 0",
             f"{judge['a_0']}", f"{judge['b_0']}", ""),
            ("skip",
             f"{judge['a_skip']}", f"{judge['b_skip']}", ""),
            ("err",
             f"{judge['a_err']}", f"{judge['b_err']}", ""),
        ]
        print_section("BENCHMARK SCORE", score_rows)
    else:
        print(f"\n{'=' * 3} BENCHMARK SCORE {'=' * (w0 + w1 + w2 + w3 - 12)}")
        print("  (未提供 --judge，跳过。用 judge/judge.py 生成后传入 xlsx 路径)")

    # ── MODEL BEHAVIOR ──
    behavior_rows = [
        ("samples (ok/total)", f"{ok_a}/{a['total']}", f"{ok_b}/{b['total']}", ""),
        ("avg total tokens",
         f"{avg(a['total_tokens'], ok_a):.0f}", f"{avg(b['total_tokens'], ok_b):.0f}",
         pct_diff(avg(a['total_tokens'], ok_a), avg(b['total_tokens'], ok_b))),
        ("avg input tokens",
         f"{avg(a['total_prompt'], ok_a):.0f}", f"{avg(b['total_prompt'], ok_b):.0f}",
         pct_diff(avg(a['total_prompt'], ok_a), avg(b['total_prompt'], ok_b))),
        ("avg output tokens",
         f"{avg(a['total_completion'], ok_a):.0f}", f"{avg(b['total_completion'], ok_b):.0f}",
         pct_diff(avg(a['total_completion'], ok_a), avg(b['total_completion'], ok_b))),
        ("avg reply length (chars)",
         f"{avg(a['total_reply_len'], ok_a):.0f}", f"{avg(b['total_reply_len'], ok_b):.0f}",
         pct_diff(avg(a['total_reply_len'], ok_a), avg(b['total_reply_len'], ok_b))),
        ("web_search tool use rate",
         f"{a['samples_with_search']}/{ok_a} ({a['samples_with_search']/ok_a*100:.1f}%)",
         f"{b['samples_with_search']}/{ok_b} ({b['samples_with_search']/ok_b*100:.1f}%)", ""),
        ("total tool calls",
         f"{a['total_tool_calls']}", f"{b['total_tool_calls']}",
         pct_diff(a['total_tool_calls'], b['total_tool_calls'])),
        ("total search calls",
         f"{a['total_search_calls']}", f"{b['total_search_calls']}",
         pct_diff(a['total_search_calls'], b['total_search_calls'])),
        ("avg search queries/call",
         f"{avg(a['total_search_queries'], a['total_search_calls']):.2f}" if a['total_search_calls'] else "N/A",
         f"{avg(b['total_search_queries'], b['total_search_calls']):.2f}" if b['total_search_calls'] else "N/A",
         pct_diff(avg(a['total_search_queries'], max(a['total_search_calls'], 1)),
                  avg(b['total_search_queries'], max(b['total_search_calls'], 1)))),
        ("article cards",
         f"{a['article_refs']} refs ({a['has_articles']}/{ok_a})",
         f"{b['article_refs']} refs ({b['has_articles']}/{ok_b})", ""),
    ]
    print_section("MODEL BEHAVIOR", behavior_rows)

    # ── SANITY CHECK ──
    def _fmt_accuracy(s):
        """format accuracy = 有引用的样本中，格式完整无残缺的比例。
        旧格式：无 unpaired PUA 即为正确；新格式：PUA 配对完整即为正确。
        """
        has_cite = max(s["has_citations"], s["has_articles"])
        if has_cite == 0:
            return "N/A"
        correct = has_cite - s["samples_with_unpaired"]
        return f"{correct}/{has_cite}"

    sw_a, sw_b = max(a['samples_with_search'], 1), max(b['samples_with_search'], 1)
    sanity_rows = [
        ("format accuracy",
         _fmt_accuracy(a), _fmt_accuracy(b), ""),
        ("cite:inline",
         f"{a['search_citations']} ({a['search_has_citations']}/{a['samples_with_search']})" if a['samples_with_search'] else "N/A",
         f"{b['search_citations']} ({b['search_has_citations']}/{b['samples_with_search']})" if b['samples_with_search'] else "N/A",
         pct_diff(a['search_citations'], b['search_citations'])),
        ("avg cite:inline/query",
         f"{avg(a['search_citations'], sw_a):.1f}",
         f"{avg(b['search_citations'], sw_b):.1f}",
         pct_diff(avg(a['search_citations'], sw_a), avg(b['search_citations'], sw_b))),
        ("cite:card",
         f"{a['search_articles']} ({a['search_has_articles']}/{a['samples_with_search']})" if a['samples_with_search'] else "N/A",
         f"{b['search_articles']} ({b['search_has_articles']}/{b['samples_with_search']})" if b['samples_with_search'] else "N/A", ""),
        ("avg cite:card/query",
         f"{avg(a['search_articles'], sw_a):.1f}",
         f"{avg(b['search_articles'], sw_b):.1f}",
         pct_diff(avg(a['search_articles'], sw_a), avg(b['search_articles'], sw_b))),
    ]
    print_section("SANITY CHECK", sanity_rows)

    # 失败的样本
    if a["fail_indices"] or b["fail_indices"]:
        print("\nFailed indices:")
        if a["fail_indices"]:
            print(f"  {label_a}: {a['fail_indices']}")
        if b["fail_indices"]:
            print(f"  {label_b}: {b['fail_indices']}")


def load_judge(xlsx_path: str, label_a: str, label_b: str) -> dict | None:
    """从 judge xlsx 中读取汇总行的分数。"""
    try:
        import pandas as pd
    except ImportError:
        print("WARNING: pandas not installed, skipping judge results", file=sys.stderr)
        return None

    df = pd.read_excel(xlsx_path, engine="openpyxl")
    summary = df[df["query"] == "SUMMARY"]
    if summary.empty:
        print(f"WARNING: no SUMMARY row in {xlsx_path}", file=sys.stderr)
        return None

    row = summary.iloc[0]

    def parse_reason(reason_str: str) -> dict:
        """Parse '1=158 | 0.5=24 | 0=33 | skip=85 | err=0'"""
        parts = {}
        for part in str(reason_str).split("|"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                parts[k.strip()] = int(v.strip())
        return parts

    result = {}
    for prefix, label in [("a", label_a), ("b", label_b)]:
        score_col = f"{label}_score"
        reason_col = f"{label}_reason"
        if score_col not in row.index:
            print(f"WARNING: column '{score_col}' not found in judge xlsx", file=sys.stderr)
            return None
        result[f"{prefix}_score"] = float(row[score_col])
        parsed = parse_reason(row[reason_col])
        result[f"{prefix}_1"] = parsed.get("1", 0)
        result[f"{prefix}_05"] = parsed.get("0.5", 0)
        result[f"{prefix}_0"] = parsed.get("0", 0)
        result[f"{prefix}_skip"] = parsed.get("skip", 0)
        result[f"{prefix}_err"] = parsed.get("err", 0)

    return result


def main():
    parser = argparse.ArgumentParser(description="对比两组 batch_chatty 输出")
    parser.add_argument("dir_a", help="对照组目录")
    parser.add_argument("dir_b", help="实验组目录")
    parser.add_argument("--label-a", default=None, help="对照组标签")
    parser.add_argument("--label-b", default=None, help="实验组标签")
    parser.add_argument("--judge", default=None, help="judge 结果 xlsx 路径")
    args = parser.parse_args()

    label_a = args.label_a or os.path.basename(args.dir_a.rstrip("/"))
    label_b = args.label_b or os.path.basename(args.dir_b.rstrip("/"))

    a = analyze_group(args.dir_a)
    b = analyze_group(args.dir_b)

    judge = None
    if args.judge:
        judge = load_judge(args.judge, label_a, label_b)

    print_comparison(a, b, label_a, label_b, judge=judge)


if __name__ == "__main__":
    main()
