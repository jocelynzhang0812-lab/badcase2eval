#!/usr/bin/env python
"""Web search timeliness script judge  搜索词年份正确性 GSB 对比评分。

比较 source (A) vs baseline (B) 的 web_search 搜索词时间正确性。

评判逻辑:
  - 通过 Langfuse trace observations 获取原始 tool_call（绕过 response_only 过滤）
  - 从 GENERATION output.tool_calls 和 TOOL observations 中提取搜索词
  - 年份必须 == 当前年份（从 trace 时间戳推算）
  - 错误少的更好

GSB 输出:
  - A 错误 < B 错误 → Good
  - A 错误 == B 错误 → Same
  - A 错误 > B 错误 → Bad

️ 已知问题 & 解决方案:
  Platform server 的 buildScriptJudgeBatchConfig 不传 judgeMode 给 script judge，
  导致 trajectory.jsonl 总是被 response_only 过滤（只保留最后一轮 user+assistant，
  删掉所有 tool_calls）。解决方案：直接通过 Langfuse API (orbit_judge._traces.fetch_trace)
  获取完整 trace observations，从中提取 tool_call 信息。

使用方法:
  1. 上传为 Platform Script Config:
     POST /api/script-configs
     {
       "name": "web_search_timeliness_judge.py",
       "script": "<本文件内容>",
       "pyprojectToml": "<见下方>",
       "uvLock": "<见下方>"
     }

  2. 通过 CLI 跑 judge:
     node Platform.mjs judge \\
       --judge-pattern script \\
       --script-config web_search_timeliness_judge.py \\
       --source-batch <A> \\
       --baseline-batch <B>

Platform 上已有配置: web_search_timeliness_judge.py (ID 同名)
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from orbit_judge import AbstractScriptJudge, JudgeContext, run_abstract_judge
from orbit_judge._traces import fetch_trace

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

YEAR_PATTERN = re.compile(r"(?<!\d)(20[1-3]\d)(?!\d)")


# ──────────────────────────────────────────────
# Trace parsing  fetch observations from Langfuse
# ──────────────────────────────────────────────

def get_search_queries_from_trace(trace_id: str) -> tuple[list[str], int]:
    """Fetch trace observations from Langfuse and extract web_search queries.

    Returns (queries, current_year).

    ️ 不能依赖 /workspace/trajectory.jsonl，因为 script judge 的 judgeMode
    固定为 response_only，会过滤掉 tool_calls。直接读 Langfuse observations。

    提取来源（按优先级）：
      1. TOOL observations: name 含 'web_search' → input.args.queries (数组)
      2. GENERATION observations: output.tool_calls[].function.arguments.queries
    """
    if not trace_id:
        return [], 0

    current_year = 0
    queries: list[str] = []

    try:
        trace = fetch_trace(trace_id)
    except Exception as e:
        print(f"Warning: failed to fetch trace {trace_id}: {e}")
        return [], 0

    # 从 trace 时间戳推断当前年份
    ts = getattr(trace, "timestamp", None)
    if isinstance(ts, datetime):
        current_year = ts.year
    elif isinstance(ts, str):
        m = re.search(r"(20[2-3]\d)", ts)
        if m:
            current_year = int(m.group(1))

    # 从 observations 中提取搜索词
    observations = getattr(trace, "observations", []) or []
    print(f"Trace {trace_id[:12]}: {len(observations)} observations")

    for obs in observations:
        obs_name = getattr(obs, "name", "") or ""
        obs_type = getattr(obs, "type", "") or ""

        # 来源 1: TOOL observations (e.g. "kosong.tool.call web_search")
        if obs_type == "TOOL" and "web_search" in obs_name.lower():
            inp = getattr(obs, "input", None)
            if isinstance(inp, dict):
                args = inp.get("args", {})
                if isinstance(args, dict):
                    _extract_queries_from_args(args, queries)

        # 来源 2: GENERATION output 中的 tool_calls
        if obs_type == "GENERATION":
            out = getattr(obs, "output", None)
            if isinstance(out, dict):
                for tc in out.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    func = tc.get("function", {})
                    if not isinstance(func, dict):
                        continue
                    if "search" not in func.get("name", "").lower():
                        continue
                    parsed_args = _parse_args(func.get("arguments", "{}"))
                    if isinstance(parsed_args, dict):
                        _extract_queries_from_args(parsed_args, queries)

    # 去重并保持顺序
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    print(f"Trace {trace_id[:12]}: extracted {len(unique)} unique queries")
    return unique, current_year


def _extract_queries_from_args(args: dict, queries: list[str]) -> None:
    """从 tool_call args 中提取 query / queries。

    web_search 工具参数格式可能是：
      - {"queries": ["q1", "q2"]}  ← kosong (AI_Platform) 格式
      - {"query": "q1"}           ← 其他模型格式
      - {"q": "q1"}               ← 简写
    """
    qs = args.get("queries", [])
    if isinstance(qs, list):
        queries.extend(str(q) for q in qs if q)
    q = args.get("query", args.get("q", ""))
    if q and isinstance(q, str):
        queries.append(q)


def _parse_args(raw: Any) -> dict:
    """Parse function arguments (may be JSON string or dict)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            result = json.loads(raw)
            return result if isinstance(result, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


# ──────────────────────────────────────────────
# 时间正确性检查
# ──────────────────────────────────────────────

def check_timeliness(queries: list[str], current_year: int) -> dict[str, Any]:
    """检查搜索词中的年份是否正确。

    规则：搜索词中出现的 4 位数年份必须等于 current_year。
    例如：current_year=2026 时，搜索 "2025年最新" → 错误。
    """
    wrong_queries = []
    with_year = 0

    for q in queries:
        years = YEAR_PATTERN.findall(q)
        if not years:
            continue
        with_year += 1
        wrong = [y for y in years if int(y) != current_year]
        if wrong:
            wrong_queries.append(f"{q} (found: {','.join(wrong)})")

    return {
        "total": len(queries),
        "with_year": with_year,
        "wrong_year_count": len(wrong_queries),
        "wrong_queries": wrong_queries,
    }


# ──────────────────────────────────────────────
# Judge
# ──────────────────────────────────────────────

class WebSearchTimelinessGSBJudge(AbstractScriptJudge):
    def evaluate(self, context: JudgeContext) -> list[dict]:
        # 从环境变量获取 trace ID
        source_trace_id = os.getenv("ORBIT_JUDGE_SOURCE_TRACE_ID", "")
        baseline_trace_id = os.getenv("ORBIT_JUDGE_BASELINE_TRACE_ID", "")

        print(f"Source trace: {source_trace_id}")
        print(f"Baseline trace: {baseline_trace_id}")

        source_queries, source_year = get_search_queries_from_trace(source_trace_id)
        baseline_queries, baseline_year = get_search_queries_from_trace(baseline_trace_id)

        # 推断年份: 优先用 source trace 的时间戳
        current_year = source_year or baseline_year or 2026
        print(f"Current year: {current_year}")

        print(f"Source queries ({len(source_queries)}): {source_queries[:5]}")
        print(f"Baseline queries ({len(baseline_queries)}): {baseline_queries[:5]}")

        # 检查时间正确性
        source_check = check_timeliness(source_queries, current_year)
        baseline_check = check_timeliness(baseline_queries, current_year)

        src_err = source_check["wrong_year_count"]
        base_err = baseline_check["wrong_year_count"]

        # GSB 判定: source 错误少 → Good（source 更好）
        if src_err < base_err:
            result = "Good"
        elif src_err == base_err:
            result = "Same"
        else:
            result = "Bad"

        comment = (
            f"Year={current_year}"
            f" | Source: {source_check['total']} queries, {source_check['with_year']} with year, {src_err} wrong"
            f" | Baseline: {baseline_check['total']} queries, {baseline_check['with_year']} with year, {base_err} wrong"
        )
        if source_check["wrong_queries"]:
            comment += f"\nSource wrong: {'; '.join(source_check['wrong_queries'][:5])}"
        if baseline_check["wrong_queries"]:
            comment += f"\nBaseline wrong: {'; '.join(baseline_check['wrong_queries'][:5])}"

        return [
            {
                "name": "gsb_comparison",
                "value": result,
                "data_type": "CATEGORICAL",
                "comment": comment,
            }
        ]


if __name__ == "__main__":
    run_abstract_judge(WebSearchTimelinessGSBJudge())
