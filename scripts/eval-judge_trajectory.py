#!/usr/bin/env python3
"""
judge_trajectory.py  通用 Trajectory Judge

不只看最终回复，而是看完整的推理轨迹（tool_call 参数、搜索结果、调用顺序等），
根据不同的 rubric 评不同维度。

用法:
    # 评搜索词质量
    python scripts/judge_trajectory.py bmk/output_dir \
        --bmk dataset.csv \
        --focus tool_calls \
        -j 20

    # 评完整轨迹（tool_call + 最终回复）
    python scripts/judge_trajectory.py bmk/output_dir \
        --bmk dataset.csv \
        --focus all \
        -j 20

    # 只评搜索相关的 tool_call
    python scripts/judge_trajectory.py bmk/output_dir \
        --bmk dataset.csv \
        --focus tool_calls \
        --tool-filter web_search \
        -j 20

环境变量:
    OPENAI_API_KEY  Internal_AI_Service API key（Judge 模型用）
"""

import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path

# ---------- 配置 ----------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
API_BASE_URL = "https://gateway.internal.ai.com/v1"
DEFAULT_MODEL = "gpt-5.4"
MAX_CONCURRENCY = 20

for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(k, None)

# ---------- Trajectory 提取 ----------

def extract_trajectory(result: dict, tool_filter: str | None = None) -> dict:
    """从 batch_chatty 输出中提取结构化的 trajectory

    返回:
        {
            "tool_calls": [{"name": "web_search", "args": {...}, "result_summary": "..."}],
            "final_response": "...",
            "search_queries": ["query1", "query2"],
            "tool_sequence": ["web_search", "web_search", "model_end"],
            "stats": {"total_tools": 2, "search_count": 2, ...}
        }
    """
    tool_calls = []
    final_response = ""
    tool_sequence = []

    for event in result.get("output", []):
        event_type = event.get("type", "")

        if event_type == "tool_end":
            tool_call_id = event.get("tool_call_id", "")
            # 提取工具名（格式：functions.web_search_xxx 或 web_search）
            tool_name = tool_call_id.split(".")[-1] if "." in tool_call_id else tool_call_id
            # 简化工具名
            for prefix in ["functions.", "functions_"]:
                tool_name = tool_name.replace(prefix, "")

            if tool_filter and tool_filter not in tool_name:
                continue

            # 提取参数和结果
            tool_result_text = ""
            for part in event.get("result_parts", []):
                if isinstance(part, dict):
                    tool_result_text += part.get("text", "")[:500]
                else:
                    tool_result_text += str(part)[:500]

            tool_calls.append({
                "name": tool_name,
                "args": event.get("tool_call_args", ""),
                "result_summary": tool_result_text[:800],
                "is_error": event.get("is_error", False),
            })
            tool_sequence.append(tool_name)

        elif event_type == "model_end":
            for c in event.get("message", {}).get("contents", []):
                text = (c.get("text") or "").strip()
                if text:
                    final_response = text
            tool_sequence.append("model_response")

            # 提取 tool_calls（模型请求中的）
            for tc in event.get("message", {}).get("tool_calls", []):
                func = tc.get("function", {})
                func_name = func.get("name", "")
                func_args = func.get("arguments", "")

                if tool_filter and tool_filter not in func_name:
                    continue

                # 尝试解析 args
                try:
                    args_dict = json.loads(func_args) if isinstance(func_args, str) else func_args
                except (json.JSONDecodeError, TypeError):
                    args_dict = func_args

                tool_calls.append({
                    "name": func_name,
                    "args": args_dict,
                    "result_summary": "",  # 结果在对应的 tool_end 里
                    "is_error": False,
                })

    # 提取搜索词
    search_queries = []
    for tc in tool_calls:
        if "search" in tc["name"].lower():
            args = tc["args"]
            if isinstance(args, dict):
                q = args.get("query", args.get("queries", ""))
                if q:
                    search_queries.append(q if isinstance(q, str) else str(q))
            elif isinstance(args, str):
                try:
                    a = json.loads(args)
                    q = a.get("query", a.get("queries", ""))
                    if q:
                        search_queries.append(q if isinstance(q, str) else str(q))
                except (json.JSONDecodeError, TypeError):
                    pass

    # 去重 tool_calls（model_end 里的和 tool_end 里的可能重复）
    seen = set()
    deduped = []
    for tc in tool_calls:
        key = f"{tc['name']}:{str(tc['args'])[:100]}"
        if key not in seen:
            seen.add(key)
            deduped.append(tc)
    tool_calls = deduped

    return {
        "tool_calls": tool_calls,
        "final_response": final_response,
        "search_queries": search_queries,
        "tool_sequence": tool_sequence,
        "stats": {
            "total_tools": len(tool_calls),
            "search_count": len(search_queries),
            "response_length": len(final_response),
        },
    }


def format_trajectory_for_judge(traj: dict, focus: str = "all") -> str:
    """把 trajectory 格式化为 Judge 能读的文本"""
    parts = []

    if focus in ("all", "tool_calls") and traj["tool_calls"]:
        parts.append("=== Tool Calls ===")
        for i, tc in enumerate(traj["tool_calls"]):
            args_str = json.dumps(tc["args"], ensure_ascii=False)[:300] if isinstance(tc["args"], dict) else str(tc["args"])[:300]
            parts.append(f"[{i+1}] {tc['name']}({args_str})")
            if tc["result_summary"]:
                parts.append(f"    → {tc['result_summary'][:200]}")
            if tc["is_error"]:
                parts.append("    ️ ERROR")

    if focus in ("all", "tool_calls") and traj["search_queries"]:
        parts.append("\n=== 搜索词 ===")
        for i, q in enumerate(traj["search_queries"]):
            parts.append(f"  [{i+1}] {q}")

    if focus in ("all", "tool_calls"):
        parts.append("\n=== 调用顺序 ===")
        parts.append(f"  {' → '.join(traj['tool_sequence'])}")

    if focus in ("all", "response"):
        parts.append("\n=== 最终回复 ===")
        parts.append(traj["final_response"][:1500])

    parts.append("\n=== 统计 ===")
    parts.append(f"  工具调用: {traj['stats']['total_tools']} 次")
    parts.append(f"  搜索次数: {traj['stats']['search_count']} 次")
    parts.append(f"  回复长度: {traj['stats']['response_length']} 字符")

    return "\n".join(parts)


# ---------- Judge ----------

JUDGE_SYSTEM_PROMPT = """你是一个评测专家，负责评估 AI 模型的推理轨迹质量。

你会收到：
1. 用户的原始问题
2. 评判标准（rubric）
3. 模型的完整推理轨迹（包含 tool call 参数、搜索词、调用顺序、最终回复）

请根据评判标准，分析轨迹中的每个关键步骤，给出评分和理由。

输出格式（严格 JSON）：
{
    "score": 0-10,
    "pass": true/false,
    "reason": "打分理由（2-3句话）",
    "issues": ["问题1", "问题2"],
    "highlights": ["做得好的点"]
}"""

JUDGE_USER_PROMPT = """## 用户问题
{query}

## 评判标准
{rubric}

## 模型推理轨迹
{trajectory}

请根据评判标准评分。"""


async def judge_single(
    client, index: int, query: str, rubric: str, traj_text: str,
    model: str, semaphore: asyncio.Semaphore,
) -> dict:
    """对单条 trajectory 打分"""
    async with semaphore:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": JUDGE_USER_PROMPT.format(
                        query=query, rubric=rubric, trajectory=traj_text
                    )},
                ],
                temperature=0.1,
                max_tokens=1000,
            )
            content = response.choices[0].message.content.strip()

            # 解析 JSON
            import re
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                result = json.loads(match.group(0))
            else:
                result = {"score": 0, "pass": False, "reason": content[:300], "issues": [], "highlights": []}

            print(f"  [{index}] score={result.get('score', '?')}/10 {'' if result.get('pass') else ''}")
            return {"index": index, "query": query[:100], **result}

        except Exception as e:
            print(f"  [{index}]  {e}")
            return {"index": index, "query": query[:100], "score": 0, "error": str(e)}


# ---------- 主流程 ----------

async def main():
    parser = argparse.ArgumentParser(description="通用 Trajectory Judge")
    parser.add_argument("batch_dir", help="batch 输出目录")
    parser.add_argument("--bmk", required=True, help="BMK 文件（CSV，含 query + rubric）")
    parser.add_argument("--focus", default="all", choices=["all", "tool_calls", "response"],
                        help="Judge 看什么：all=全部, tool_calls=只看工具调用, response=只看回复")
    parser.add_argument("--tool-filter", default=None, help="只看特定工具（如 web_search）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Judge 模型")
    parser.add_argument("-j", "--concurrency", type=int, default=MAX_CONCURRENCY)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("-o", "--output", default=None)
    args = parser.parse_args()

    if not OPENAI_API_KEY:
        print(" 请设置 OPENAI_API_KEY")
        sys.exit(1)

    # 读取 batch 结果
    batch_dir = Path(args.batch_dir)
    result_files = sorted(batch_dir.glob("*.json"), key=lambda f: int(f.stem) if f.stem.isdigit() else 0)
    if args.limit:
        result_files = result_files[:args.limit]

    results = []
    for f in result_files:
        with open(f) as fh:
            results.append(json.load(fh))

    # 读取 BMK
    queries, rubrics = {}, {}
    with open(args.bmk, encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            queries[i] = row.get("query", "")
            rubrics[i] = row.get("rubric", row.get("打分点", row.get("ground_truth", "")))

    print(f" {len(results)} 条结果, focus={args.focus}, tool_filter={args.tool_filter}")

    # 提取 trajectory
    trajectories = []
    for i, result in enumerate(results):
        traj = extract_trajectory(result, args.tool_filter)
        traj_text = format_trajectory_for_judge(traj, args.focus)
        trajectories.append((traj, traj_text))

    # 统计
    total_tools = sum(t[0]["stats"]["total_tools"] for t in trajectories)
    total_searches = sum(t[0]["stats"]["search_count"] for t in trajectories)
    print(f" 共 {total_tools} 次工具调用, {total_searches} 次搜索\n")

    # Judge
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=API_BASE_URL)
    semaphore = asyncio.Semaphore(args.concurrency)

    tasks = []
    for i, (traj, traj_text) in enumerate(trajectories):
        query = queries.get(i, results[i].get("query", f"[row {i}]"))
        rubric = rubrics.get(i, "评估模型的推理轨迹质量")
        tasks.append(judge_single(client, i, query, rubric, traj_text, args.model, semaphore))

    print(f"️ Judging {len(tasks)} 条 (并发 {args.concurrency})...\n")
    all_results = await asyncio.gather(*tasks)

    # 汇总
    scored = [r for r in all_results if "score" in r and not r.get("error")]
    if scored:
        avg = sum(r["score"] for r in scored) / len(scored)
        passed = sum(1 for r in scored if r.get("pass"))
        print(f"\n{'=' * 50}")
        print(" Trajectory Judge 结果")
        print(f"   总数: {len(all_results)}")
        print(f"   有效: {len(scored)}")
        print(f"   平均分: {avg:.1f}/10")
        print(f"   通过率: {passed}/{len(scored)} ({passed/len(scored):.0%})")

        # 常见问题
        all_issues = []
        for r in scored:
            all_issues.extend(r.get("issues", []))
        if all_issues:
            from collections import Counter
            print("\n   常见问题:")
            for issue, cnt in Counter(all_issues).most_common(5):
                print(f"     [{cnt}次] {issue}")

    # 输出
    output_path = args.output or f"traj_judge_result/{Path(args.bmk).stem}.jsonl"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n 结果: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
