#!/usr/bin/env python3
"""
分数计算脚本  从 Platform batch 获取分数并计算加权平均

用法:
    # 单个 batch 算分
    python3 calculate_scores.py 75469

    # 多个 batch 加权平均
    python3 calculate_scores.py 75469 75470 75471

    # Arena 模式（使用 Arena 特殊公式）
    python3 calculate_scores.py --arena 75469 75470

    # Toolcall_Action_V2 模式（NUMERIC 用 avg×100）
    python3 calculate_scores.py --toolcall-action-v2 75469

    # 输出 JSON 格式（方便程序调用）
    python3 calculate_scores.py --json 75469 75470

环境变量:
    AuthGateway_ACCESS_TOKEN: Platform 认证 token（必需）
"""

import subprocess
import json
import sys
import os
import argparse
from typing import List, Dict, Optional, Any


ORBIT_API_BASE = "https://platform.internal.ai.com"


def get_orbit_path() -> str:
    """定位 Platform CLI 路径"""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Platform"),
        os.path.expanduser("~/.AI_Platform/skills/Platform"),
    ]
    for path in candidates:
        if os.path.isfile(os.path.join(path, "Platform.mjs")):
            return path
    print("错误：无法找到 Platform CLI", file=sys.stderr)
    sys.exit(1)


def run_orbit_cmd(orbit_path: str, args: str) -> Optional[Dict]:
    """执行 Platform CLI 命令并解析 JSON 输出"""
    cmd = f"node Platform.mjs {args}"
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=orbit_path,
        env={**os.environ, "AuthGateway_ACCESS_TOKEN": os.environ.get("AuthGateway_ACCESS_TOKEN", "")}
    )
    if result.returncode != 0:
        print(f"CLI 命令失败: {cmd}\n{result.stderr}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"JSON 解析失败: {result.stdout[:200]}", file=sys.stderr)
        return None


def collect_trace_ids(batch_id: str, orbit_path: str) -> List[str]:
    """收集 batch 的所有 traceIds（分页）"""
    trace_ids = []
    page = 1
    while True:
        data = run_orbit_cmd(orbit_path, f"tasks --batch {batch_id} --page {page} --page-size 100")
        if not data:
            break
        tasks = data.get("tasks", [])
        if not tasks:
            break
        for task in tasks:
            tid = task.get("traceId")
            if tid:
                trace_ids.append(tid)
        total_pages = data.get("totalPages", 1)
        if page >= total_pages:
            break
        page += 1
    return trace_ids


def get_score_stats(batch_id: str, orbit_path: str) -> Optional[Dict]:
    """通过 scores CLI 获取分数统计"""
    return run_orbit_cmd(orbit_path, f"scores --batch {batch_id}")


def get_batch_info(batch_id: str, orbit_path: str) -> Optional[Dict]:
    """获取 batch 基本信息"""
    return run_orbit_cmd(orbit_path, f"describe --batch {batch_id}")


def parse_scores_from_stats(
    scores_data: Dict,
    arena_mode: bool = False,
    toolcall_action_v2_mode: bool = False,
) -> List[Dict[str, Any]]:
    """从 score-stats 数据解析分数

    Args:
        scores_data: scores CLI 返回的原始数据
        arena_mode: 是否使用 Arena 特殊公式 (Better=1, Same=0.5, Worse=0)
        toolcall_action_v2_mode: 是否对 NUMERIC 用 avg×100 而非 avg×count
    """
    all_rows = scores_data.get("byJudgeBatch", {}).get("__all__", {}).get("rows", [])
    results = []

    for row in all_rows:
        score_name = row.get("name", "")
        count = row.get("count", 0)
        data_type = row.get("dataType", "")
        distribution = row.get("distribution", {})

        if data_type == "NUMERIC":
            avg = row.get("avg", 0)
            if toolcall_action_v2_mode and "Toolcall_Action_V2" in score_name:
                final_score = round(avg * 100, 2)
            else:
                final_score = round(avg * count, 2)
            results.append({
                "score_name": score_name,
                "data_type": "NUMERIC",
                "avg_score": avg,
                "count": count,
                "final_score": final_score,
            })

        elif data_type == "CATEGORICAL":
            if arena_mode and ("Better" in distribution or "Same" in distribution or "Worse" in distribution):
                # Arena 特殊公式: (Better×1 + Same×0.5 + Worse×0) / 总数 × 100
                better = distribution.get("Better", 0)
                same = distribution.get("Same", 0)
                worse = distribution.get("Worse", distribution.get(" Worse", 0))
                total_count = better + same + worse
                if total_count == 0:
                    percentage = 0.0
                else:
                    total_score = better * 1 + same * 0.5 + worse * 0
                    percentage = round((total_score / total_count) * 100, 2)
                results.append({
                    "score_name": score_name,
                    "data_type": "CATEGORICAL",
                    "better": better,
                    "same": same,
                    "worse": worse,
                    "total": total_count,
                    "percentage": percentage,
                    "formula": "arena",
                })
            elif "Better" in distribution or "Worse" in distribution or " Worse" in distribution:
                # 标准 CATEGORICAL: Better / (Better + Worse) × 100
                # ️ 不包含 Same（Arena 请用 --arena 模式）
                better = distribution.get("Better", 0)
                worse = distribution.get("Worse", distribution.get(" Worse", 0))
                total = better + worse
                percentage = round(better / total * 100, 2) if total > 0 else 0
                results.append({
                    "score_name": score_name,
                    "data_type": "CATEGORICAL",
                    "better": better,
                    "worse": worse,
                    "total": total,
                    "percentage": percentage,
                    "formula": "standard",
                })
            elif "True" in distribution or "False" in distribution:
                true_count = distribution.get("True", 0)
                false_count = distribution.get("False", 0)
                total = true_count + false_count
                percentage = round(true_count / total * 100, 2) if total > 0 else 0
                results.append({
                    "score_name": score_name,
                    "data_type": "BOOLEAN",
                    "true_count": true_count,
                    "false_count": false_count,
                    "total": total,
                    "percentage": percentage,
                })

        elif data_type == "BOOLEAN":
            true_count = distribution.get("True", 0)
            false_count = distribution.get("False", 0)
            total = true_count + false_count
            percentage = round(true_count / total * 100, 2) if total > 0 else 0
            results.append({
                "score_name": score_name,
                "data_type": "BOOLEAN",
                "true_count": true_count,
                "false_count": false_count,
                "total": total,
                "percentage": percentage,
            })

    return results


def categorize_score(score_name: str) -> str:
    """根据评分项名称分类: vibe / baseline / single / 原始名"""
    name_lower = score_name.lower()
    if "vibe" in name_lower:
        return "vibe"
    elif "底线" in score_name:
        return "baseline"
    elif "单向" in score_name:
        return "single"
    else:
        return score_name


def calculate_weighted_average(all_scores: List[List[Dict]], arena_mode: bool = False) -> Dict:
    """多 batch 加权平均

    Args:
        all_scores: 每个 batch 的分数列表
        arena_mode: 是否使用 Arena 加权公式

    Returns:
        {
            "by_score_name": { score_name: { aggregated stats } },
            "by_category": { "vibe": {...}, "baseline": {...}, "single": {...} },
        }
    """
    # 按 score_name 聚合
    agg: Dict[str, Dict] = {}
    for batch_scores in all_scores:
        for s in batch_scores:
            name = s["score_name"]
            if name not in agg:
                agg[name] = {
                    "data_type": s["data_type"],
                    "better": 0,
                    "worse": 0,
                    "same": 0,
                    "total": 0,
                    "count": 0,
                    "avg_sum": 0.0,
                    "final_score_sum": 0.0,
                }
            a = agg[name]
            # CATEGORICAL uses better/worse, BOOLEAN uses true_count/false_count
            a["better"] += s.get("better", s.get("true_count", 0))
            a["worse"] += s.get("worse", s.get("false_count", 0))
            a["same"] += s.get("same", 0)
            a["total"] += s.get("total", s.get("count", 0))
            if s["data_type"] == "NUMERIC":
                a["count"] += s.get("count", 0)
                a["avg_sum"] += s.get("avg_score", 0) * s.get("count", 0)
                a["final_score_sum"] += s.get("final_score", 0)

    # 计算每个 score_name 的最终值
    by_name = {}
    for name, a in agg.items():
        if a["data_type"] == "NUMERIC":
            weighted_avg = a["avg_sum"] / a["count"] if a["count"] > 0 else 0
            by_name[name] = {
                "data_type": "NUMERIC",
                "avg": round(weighted_avg, 4),
                "count": a["count"],
                "final_score": round(a["final_score_sum"], 2),
            }
        elif arena_mode and a["same"] > 0:
            total = a["better"] + a["same"] + a["worse"]
            score = (a["better"] * 1 + a["same"] * 0.5) / total * 100 if total > 0 else 0
            by_name[name] = {
                "data_type": "CATEGORICAL",
                "better": a["better"],
                "same": a["same"],
                "worse": a["worse"],
                "total": total,
                "percentage": round(score, 2),
                "formula": "arena",
            }
        else:
            total = a["better"] + a["worse"]
            pct = round(a["better"] / total * 100, 2) if total > 0 else 0
            by_name[name] = {
                "data_type": a["data_type"],
                "better": a["better"],
                "worse": a["worse"],
                "total": total,
                "percentage": pct,
            }

    # 按 category 分组
    cats: Dict[str, Dict] = {}
    for name, v in by_name.items():
        if v["data_type"] == "NUMERIC":
            continue  # NUMERIC 不参与分类汇总
        cat = categorize_score(name)
        if cat not in cats:
            cats[cat] = {"better": 0, "worse": 0, "same": 0, "total": 0, "items": []}
        c = cats[cat]
        c["better"] += v.get("better", 0)
        c["worse"] += v.get("worse", 0)
        c["same"] += v.get("same", 0)
        c["total"] += v.get("total", 0)
        c["items"].append(name)

    by_category = {}
    for cat, c in cats.items():
        if arena_mode and c["same"] > 0:
            total = c["better"] + c["same"] + c["worse"]
            pct = round((c["better"] * 1 + c["same"] * 0.5) / total * 100, 2) if total > 0 else 0
        else:
            total = c["better"] + c["worse"]
            pct = round(c["better"] / total * 100, 2) if total > 0 else 0
        by_category[cat] = {
            "better": c["better"],
            "worse": c["worse"],
            "total": total,
            "percentage": pct,
            "item_count": len(c["items"]),
            "items": c["items"],
        }

    return {"by_score_name": by_name, "by_category": by_category}


def print_scores_table(batch_id: str, scores: List[Dict], dataset_name: str = ""):
    """格式化输出单个 batch 的分数"""
    header = f"Batch {batch_id}"
    if dataset_name:
        header += f" ({dataset_name})"
    print(f"\n{'='*60}")
    print(header)
    print(f"{'='*60}")

    for s in scores:
        name = s["score_name"]
        dtype = s["data_type"]
        if dtype == "NUMERIC":
            print(f"  {name}: final={s['final_score']} (avg={s['avg_score']:.4f}, count={s['count']})")
        elif s.get("formula") == "arena":
            print(f"  {name}: {s['percentage']}% (Better={s['better']}, Same={s['same']}, Worse={s['worse']}) [Arena]")
        elif s["data_type"] == "BOOLEAN":
            print(f"  {name}: {s['percentage']}% ({s.get('true_count', s.get('better', 0))}/{s['total']})")
        else:
            print(f"  {name}: {s['percentage']}% ({s.get('better', 0)}/{s['total']})")


def print_weighted_summary(summary: Dict):
    """格式化输出加权平均汇总"""
    print(f"\n{'='*60}")
    print("加权平均汇总")
    print(f"{'='*60}")

    print("\n--- 按评分项 ---")
    for name, v in summary["by_score_name"].items():
        dtype = v["data_type"]
        if dtype == "NUMERIC":
            print(f"  {name}: final={v['final_score']} (avg={v['avg']:.4f}, count={v['count']})")
        elif v.get("formula") == "arena":
            print(f"  {name}: {v['percentage']}% (Better={v['better']}, Same={v['same']}, Worse={v['worse']}) [Arena]")
        else:
            print(f"  {name}: {v['percentage']}% ({v.get('better', 0)}/{v['total']})")

    if summary["by_category"]:
        print("\n--- 按分类 ---")
        for cat, v in summary["by_category"].items():
            print(f"  [{cat}] {v['percentage']}% ({v['better']}/{v['total']}, {v['item_count']} items)")


def main():
    parser = argparse.ArgumentParser(
        description="Platform 分数计算脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 calculate_scores.py 75469              # 单 batch
  python3 calculate_scores.py 75469 75470 75471  # 多 batch 加权
  python3 calculate_scores.py --arena 75469      # Arena 模式
  python3 calculate_scores.py --json 75469       # JSON 输出
        """,
    )
    parser.add_argument("batch_ids", nargs="+", help="Batch IDs")
    parser.add_argument("--arena", action="store_true", help="使用 Arena 特殊公式 (Better=1, Same=0.5)")
    parser.add_argument("--toolcall-action-v2", action="store_true", help="Toolcall_Action_V2 的 NUMERIC 用 avg×100")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    args = parser.parse_args()
    orbit_path = get_orbit_path()

    all_scores = []

    for batch_id in args.batch_ids:
        # 获取 batch 信息
        info = get_batch_info(batch_id, orbit_path)
        dataset_name = ""
        if info:
            dataset_name = info.get("config", {}).get("datasetName", "")

        # 获取分数
        scores_data = get_score_stats(batch_id, orbit_path)
        if not scores_data:
            print(f"️ Batch {batch_id} 无分数数据", file=sys.stderr)
            continue

        scores = parse_scores_from_stats(
            scores_data,
            arena_mode=args.arena,
            toolcall_action_v2_mode=args.toolcall_action_v2,
        )
        all_scores.append(scores)

        if not args.json:
            print_scores_table(batch_id, scores, dataset_name)

    # 多 batch 加权平均
    if len(all_scores) > 1:
        summary = calculate_weighted_average(all_scores, arena_mode=args.arena)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print_weighted_summary(summary)
    elif len(all_scores) == 1 and args.json:
        print(json.dumps(all_scores[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
