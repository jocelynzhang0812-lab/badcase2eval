#!/usr/bin/env python3
"""
Judge script: 对多组 batch 结果用 LLM 打分，输出对比表格。

用法:
    python judge/judge.py bmk/badcase_bmk_no_hook bmk/badcase_bmk_with_hook \\
        --bmk "bmk/xxx.xlsx" \\
        --label no_hook with_hook \\
        --limit 5 -j 40

输出: judge/result/{bmk_stem}.xlsx
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_prompt.prompt as prompt_simple
import judge_prompt.prompt_wenxin as prompt_wenxin

# ---------- 配置 ----------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ai_service_BASE_URL = "https://gateway.internal.ai.com/v1"
JUDGE_MODEL = "gpt-5.4"
MAX_CONCURRENCY = 40
PROMPT_MODE = "wenxin"  # "simple" or "wenxin"

# 运行时由 main() 设置
SYSTEM_PROMPT = ""
user_prompt_at_1 = None

# ---------- 辅助函数 ----------


def extract_model_response(result: dict) -> str:
    """从 batch 输出 JSON 中提取模型最终回复文本（取最后一个非空 model_end text）。"""
    final = ""
    for event in result.get("output", []):
        if event.get("type") == "model_end":
            for c in event.get("message", {}).get("contents", []):
                text = (c.get("text") or "").strip()
                if text:
                    final = text
    return final


def extract_search_meta(result: dict) -> str:
    """从 batch 输出 JSON 中提取搜索结果引用信息。

    取 tool_end 事件中 tool_call_id 以 functions.web_search 开头的，
    从 result_parts[].text 中提取 [^N^](URL) title (date) 格式的引用。
    """
    citations = []
    pattern = re.compile(
        r'\[\^(\d+)\^\]\((https?://[^\)]+)\)\s+([^\n]+?)\s+\((\d{4}-\d{2}-\d{2})\)'
    )
    for event in result.get("output", []):
        if event.get("type") != "tool_end":
            continue
        if not event.get("tool_call_id", "").startswith("functions.web_search"):
            continue
        for part in event.get("result_parts", []):
            text = part.get("text", "") if isinstance(part, dict) else str(part)
            for m in pattern.finditer(text):
                citations.append(m.group(0))
    return "\n".join(citations)


def check_tool_usage(result: dict) -> tuple[bool, str]:
    """检查样本的 tool 使用情况，决定是否应该 judge。

    Returns:
        (should_judge, skip_reason)
        - should_judge=True: 只用了 web_search，可以 judge
        - should_judge=False: 跳过，skip_reason 说明原因
    """
    tool_names = set()
    for event in result.get("output", []):
        if event.get("type") == "model_end":
            for tc in event.get("message", {}).get("tool_calls", []):
                name = tc.get("function", {}).get("name", "")
                if name:
                    tool_names.add(name)
    if "web_search" not in tool_names:
        return False, "SKIP: no web_search"
    other_tools = tool_names - {"web_search"}
    if other_tools:
        return False, f"SKIP: has non-search tools ({', '.join(sorted(other_tools))})"
    return True, ""


def load_bmk(bmk_path: str) -> pd.DataFrame:
    """加载 BMK 文件（xlsx 或 csv）。"""
    p = Path(bmk_path)
    if p.suffix == ".xlsx":
        return pd.read_excel(p)
    else:
        return pd.read_csv(p)


DIMENSIONS = ["timeliness", "authority", "information_completeness", "citation_compliance"]


async def judge_one(
    client: AsyncOpenAI,
    index: int,
    query: str,
    criteria: str,
    model_response: str,
    search_meta: str,
    sem: asyncio.Semaphore,
) -> dict:
    """调用 judge 模型评估单条样本。根据 PROMPT_MODE 走不同解析逻辑。"""
    if not model_response.strip():
        if PROMPT_MODE == "simple":
            return {"index": index, "judge_raw": "", "score": 0, "reason": "Empty model response."}
        else:
            dims = {d + "_score": 0 for d in DIMENSIONS}
            dims.update({d + "_reason": "Empty model response." for d in DIMENSIONS})
            return {"index": index, "judge_raw": "", **dims}

    if PROMPT_MODE == "simple":
        prompt = user_prompt_at_1(query, criteria, model_response)
    else:
        prompt = user_prompt_at_1(query, model_response, search_meta, criteria)

    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=1024,
            )
            content = resp.choices[0].message.content or ""
            parsed = json.loads(content)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}

            if PROMPT_MODE == "simple":
                return {
                    "index": index,
                    "judge_raw": content,
                    "score": parsed.get("score", 0),
                    "reason": parsed.get("reason", ""),
                }
            else:
                normalized = {}
                for k, v in parsed.items():
                    nk = k.strip().lower().replace(" ", "_")
                    normalized[nk] = v
                result = {"index": index, "judge_raw": content}
                for d in DIMENSIONS:
                    dim_data = normalized.get(d, {})
                    result[d + "_score"] = dim_data.get("score", 0)
                    result[d + "_reason"] = dim_data.get("reason", "")
                return result
        except Exception as e:
            if PROMPT_MODE == "simple":
                return {"index": index, "judge_raw": f"ERROR: {e}", "score": None, "reason": f"Judge error: {e}"}
            else:
                dims = {d + "_score": None for d in DIMENSIONS}
                dims.update({d + "_reason": f"Judge error: {e}" for d in DIMENSIONS})
                return {"index": index, "judge_raw": f"ERROR: {e}", **dims}


async def judge_dir(
    client: AsyncOpenAI,
    result_dir: Path,
    bmk_df: pd.DataFrame,
    label: str,
    sem: asyncio.Semaphore,
    limit: int | None = None,
) -> list[dict]:
    """对一个 batch 结果目录进行 judge 评估。"""
    total = min(len(bmk_df), limit) if limit else len(bmk_df)
    done_count = 0
    results: list[dict] = [None] * total

    async def run_one(i: int) -> dict:
        nonlocal done_count
        result_file = result_dir / f"{i}.json"
        if not result_file.exists():
            return {"index": i, "score": None, "reason": "Result file missing."}

        with open(result_file, "r", encoding="utf-8") as f:
            batch_result = json.load(f)

        # 检查 tool 使用情况，决定是否跳过
        should_judge, skip_reason = check_tool_usage(batch_result)
        if not should_judge:
            if PROMPT_MODE == "simple":
                r = {"index": i, "_skip": True, "judge_raw": "", "score": "SKIP", "reason": skip_reason}
            else:
                skip_dims = {d + "_score": "SKIP" for d in DIMENSIONS}
                skip_dims.update({d + "_reason": skip_reason for d in DIMENSIONS})
                r = {"index": i, "_skip": True, "judge_raw": "", **skip_dims}
            results[i] = r
            done_count += 1
            print(f"  [{label}] [{done_count}/{total}] #{i} {skip_reason}", flush=True)
            return r

        query = bmk_df.iloc[i]["query"]
        criteria = str(bmk_df.iloc[i].get("打分点", ""))
        if not criteria.strip() or criteria == "nan":
            gt = str(bmk_df.iloc[i].get("ground_truth", ""))
            if gt.strip() and gt != "nan":
                criteria = f"The correct answer is: {gt}"
        model_response = extract_model_response(batch_result)
        search_meta = extract_search_meta(batch_result)

        r = await judge_one(client, i, query, criteria, model_response, search_meta, sem)
        results[i] = r

        done_count += 1
        if PROMPT_MODE == "simple":
            s = r.get("score", "?")
            reason = (r.get("reason") or "")[:80]
            print(f"  [{label}] [{done_count}/{total}] #{i} score={s} | {reason}", flush=True)
        else:
            scores = [str(r.get(d + "_score", "?")) for d in DIMENSIONS]
            print(f"  [{label}] [{done_count}/{total}] #{i} T={scores[0]} A={scores[1]} IC={scores[2]} Ci={scores[3]}", flush=True)
        return r

    tasks = [run_one(i) for i in range(total)]
    await asyncio.gather(*tasks)
    return results


def build_result_table(
    bmk_df: pd.DataFrame,
    all_results: dict[str, list[dict]],
    limit: int | None = None,
) -> pd.DataFrame:
    """构建对比表格。"""
    total = min(len(bmk_df), limit) if limit else len(bmk_df)
    labels = list(all_results.keys())

    rows = []
    for i in range(total):
        row = {
            "index": i,
            "query": bmk_df.iloc[i]["query"],
            "criteria": str(bmk_df.iloc[i].get("打分点", "") or bmk_df.iloc[i].get("ground_truth", "")),
        }
        for label in labels:
            r = all_results[label][i]
            if PROMPT_MODE == "simple":
                row[f"{label}_score"] = r.get("score") if r else None
                row[f"{label}_reason"] = r.get("reason", "") if r else ""
                row[f"{label}_judge_raw"] = r.get("judge_raw", "") if r else ""
            else:
                if r:
                    for d in DIMENSIONS:
                        row[f"{label}_{d}_score"] = r.get(d + "_score")
                        row[f"{label}_{d}_reason"] = r.get(d + "_reason", "")
                    row[f"{label}_judge_raw"] = r.get("judge_raw", "")
                else:
                    for d in DIMENSIONS:
                        row[f"{label}_{d}_score"] = None
                        row[f"{label}_{d}_reason"] = ""
                    row[f"{label}_judge_raw"] = ""
        rows.append(row)

    df = pd.DataFrame(rows)

    # 汇总行（排除 SKIP）
    summary_row = {"index": "", "query": "SUMMARY", "criteria": ""}
    for label in labels:
        non_skip = [r for r in all_results[label] if r and not r.get("_skip")]
        skipped = [r for r in all_results[label] if r and r.get("_skip")]
        if PROMPT_MODE == "simple":
            scored = [r for r in non_skip if isinstance(r.get("score"), (int, float))]
            errs = [r for r in non_skip if r.get("score") is None]
            avg = sum(r["score"] for r in scored) / len(scored) if scored else 0
            n1 = sum(1 for r in scored if r["score"] == 1)
            n05 = sum(1 for r in scored if r["score"] == 0.5)
            n0 = sum(1 for r in scored if r["score"] == 0)
            summary_row[f"{label}_score"] = round(avg, 4)
            summary_row[f"{label}_reason"] = f"1={n1} | 0.5={n05} | 0={n0} | skip={len(skipped)} | err={len(errs)}"
        else:
            for d in DIMENSIONS:
                scored = [r for r in non_skip if isinstance(r.get(d + "_score"), (int, float))]
                errs = [r for r in non_skip if r.get(d + "_score") is None]
                avg = sum(r[d + "_score"] for r in scored) / len(scored) if scored else 0
                n1 = sum(1 for r in scored if r[d + "_score"] == 1)
                n0 = sum(1 for r in scored if r[d + "_score"] == 0)
                summary_row[f"{label}_{d}_score"] = round(avg, 4)
                summary_row[f"{label}_{d}_reason"] = f"pass={n1} | fail={n0} | skip={len(skipped)} | err={len(errs)}"
    df = pd.concat([df, pd.DataFrame([summary_row])], ignore_index=True)

    return df


async def main():
    global JUDGE_MODEL, MAX_CONCURRENCY, PROMPT_MODE, SYSTEM_PROMPT, user_prompt_at_1

    parser = argparse.ArgumentParser(description="Judge batch result dirs and output comparison table")
    parser.add_argument("dirs", nargs="+", help="Batch result directories to judge")
    parser.add_argument("--bmk", required=True, help="BMK file (xlsx/csv) with query and 打分点")
    parser.add_argument("--label", nargs="+", default=None, help="Labels for each dir (default: dir names)")
    parser.add_argument("--limit", type=int, default=None, help="Only judge first N samples")
    parser.add_argument("--model", default=JUDGE_MODEL, help=f"Judge model (default: {JUDGE_MODEL})")
    parser.add_argument("--prompt", choices=["simple", "wenxin"], default="wenxin", help="Prompt mode (default: wenxin)")
    parser.add_argument("-j", "--concurrency", type=int, default=MAX_CONCURRENCY, help="Max concurrency")
    args = parser.parse_args()

    JUDGE_MODEL = args.model
    MAX_CONCURRENCY = args.concurrency
    PROMPT_MODE = args.prompt
    if PROMPT_MODE == "simple":
        SYSTEM_PROMPT = prompt_simple.SYSTEM_PROMPT
        user_prompt_at_1 = prompt_simple.user_prompt_at_1
    else:
        SYSTEM_PROMPT = prompt_wenxin.SYSTEM_PROMPT
        user_prompt_at_1 = prompt_wenxin.user_prompt_at_1

    labels = args.label if args.label and len(args.label) == len(args.dirs) else [Path(d).name for d in args.dirs]

    bmk_df = load_bmk(args.bmk)
    bmk_stem = Path(args.bmk).stem
    print(f"BMK: {args.bmk} ({len(bmk_df)} rows)")
    print(f"Judge model: {JUDGE_MODEL}")
    print(f"Concurrency: {MAX_CONCURRENCY}")

    import httpx
    http_client = httpx.AsyncClient(verify=True, proxy=None)
    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=ai_service_BASE_URL,
        http_client=http_client,
    )
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    all_results: dict[str, list[dict]] = {}
    for d, label in zip(args.dirs, labels):
        result_dir = Path(d)
        print(f"\nJudging: {result_dir} (label={label})")
        results = await judge_dir(client, result_dir, bmk_df, label, sem, limit=args.limit)
        all_results[label] = results

    await http_client.aclose()

    # 构建表格并保存
    out_dir = Path("judge/result")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{bmk_stem}.xlsx"

    df = build_result_table(bmk_df, all_results, limit=args.limit)
    df.to_excel(out_path, index=False, engine="openpyxl")
    print(f"\nResult saved to: {out_path}")

    # 打印汇总
    summary = df.iloc[-1]
    print(f"\n{'='*70}")
    for label in labels:
        print(f"  [{label}]")
        if PROMPT_MODE == "simple":
            print(f"    avg_score={summary[f'{label}_score']}  ({summary[f'{label}_reason']})")
        else:
            for d in DIMENSIONS:
                print(f"    {d:>26s}: avg={summary[f'{label}_{d}_score']}  ({summary[f'{label}_{d}_reason']})")
        print()
    print(f"{'='*70}")


if __name__ == "__main__":
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(k, None)
    asyncio.run(main())
