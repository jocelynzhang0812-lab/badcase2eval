#!/usr/bin/env python3
"""
Batch 批量监控脚本

用法:
    python3 batch_monitor.py 74402 74403 74404           # 查询一次
    python3 batch_monitor.py --watch 74402 --interval 5m  # 持续监控
    python3 batch_monitor.py --check 74402 74403          # 仅检查完成
"""

import subprocess
import json
import sys
import time
import argparse
import os
from typing import List, Dict, Optional


def get_orbit_path() -> str:
    """定位 Platform CLI 路径

    查找顺序:
    1. 脚本所在目录的兄弟 Platform/ (即 skills/Platform/)
    2. ~/.AI_Platform/skills/Platform/
    """
    # 基于脚本自身位置查找，避免 CWD 依赖
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)  # scripts/ -> project root

    candidates = [
        os.path.join(project_root, "skills", "Platform"),  # skills/Platform/ (or symlink)
        os.path.expanduser("~/.AI_Platform/skills/Platform"),
    ]

    for path in candidates:
        resolved = os.path.realpath(path)  # resolve symlinks
        if os.path.isfile(os.path.join(resolved, "Platform.mjs")):
            return resolved

    print("错误：无法找到 Platform CLI（已检查 skills/Platform/ 和 ~/.AI_Platform/skills/Platform/）")
    sys.exit(1)


def run_describe(batch_id: str, orbit_path: str) -> Dict:
    """执行 Platform describe 并解析结果"""
    cmd = f"node Platform.mjs describe {batch_id}"
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=orbit_path,
        env={**os.environ, "AuthGateway_ACCESS_TOKEN": os.environ.get("AuthGateway_ACCESS_TOKEN", "")}
    )

    if result.returncode != 0:
        print(f"Error describing batch {batch_id}: {result.stderr}")
        return {}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Error parsing JSON for batch {batch_id}")
        return {}


def format_progress(data: Dict) -> str:
    """格式化进度信息"""
    progress = data.get("progress", {})
    status = progress.get("batchStatus", "unknown")
    total = progress.get("totalTasks", 0)
    succeeded = progress.get("succeededTasks", 0)
    failed = progress.get("failedTasks", 0)
    running = progress.get("runningTasks", 0)
    pending = progress.get("pendingTasks", 0)

    fail_rate = (failed / total * 100) if total > 0 else 0

    lines = [
        f"状态: {status}",
        f"进度: {succeeded}/{total} (运行中: {running}, 待处理: {pending}, 失败: {failed}, {fail_rate:.1f}%)"
    ]

    if fail_rate > 20:
        lines.append("️ 警告: 失败率超过 20%")

    if status == "finished":
        lines.append(" 已完成")
    elif status == "failed":
        lines.append(" 失败")
    elif status == "running":
        lines.append(" 运行中")
    elif status == "pending":
        lines.append(" 等待中")

    return "\n".join(lines)


def get_scores(batch_id: str, orbit_path: str) -> Optional[Dict]:
    """获取分数"""
    cmd = f"node Platform.mjs scores {batch_id}"
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=orbit_path,
        env={**os.environ, "AuthGateway_ACCESS_TOKEN": os.environ.get("AuthGateway_ACCESS_TOKEN", "")}
    )

    if result.returncode != 0:
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def monitor_once(batch_ids: List[str], orbit_path: str) -> Dict[str, Dict]:
    """监控一次所有 batch"""
    results = {}
    for batch_id in batch_ids:
        print(f"\n=== Batch {batch_id} ===")
        data = run_describe(batch_id, orbit_path)
        if data:
            print(format_progress(data))
            results[batch_id] = data
    return results


def monitor_watch(batch_ids: List[str], interval: int, orbit_path: str):
    """持续监控直到全部完成"""
    iteration = 0
    while True:
        iteration += 1
        print(f"\n{'='*50}")
        print(f"第 {iteration} 次检查 ({time.strftime('%Y-%m-%d %H:%M:%S')})")
        print('='*50)

        results = monitor_once(batch_ids, orbit_path)

        all_finished = all(
            r.get("progress", {}).get("batchStatus") in ["finished", "failed"]
            for r in results.values()
        )

        if all_finished:
            print("\n" + "="*50)
            print(" 所有 batch 已完成！")
            print("="*50)

            for batch_id in batch_ids:
                print(f"\n--- Batch {batch_id} 分数 ---")
                scores = get_scores(batch_id, orbit_path)
                if scores:
                    by_all = scores.get("byJudgeBatch", {}).get("__all__", {})
                    rows = by_all.get("rows", [])
                    for row in rows:
                        name = row.get("name", "")
                        data_type = row.get("dataType", "")
                        dist = row.get("distribution", {})
                        if data_type == "NUMERIC":
                            avg = row.get("avg", 0)
                            count = row.get("count", 0)
                            print(f"  {name}: {avg * 100:.2f}% (avg={avg:.4f}, count={count})")
                        elif "Better" in dist or "Worse" in dist:
                            better = dist.get("Better", 0)
                            # Platform API sometimes returns ' Worse' (with leading space)
                            worse = dist.get("Worse", dist.get(" Worse", 0))
                            total = better + worse
                            pct = better / total * 100 if total > 0 else 0
                            print(f"  {name}: {better}/{total} ({pct:.2f}%)")
                        elif "True" in dist or "False" in dist:
                            true_count = dist.get("True", 0)
                            false_count = dist.get("False", 0)
                            total = true_count + false_count
                            pct = true_count / total * 100 if total > 0 else 0
                            print(f"  {name}: {true_count}/{total} ({pct:.2f}%)")
            break

        print(f"\n 等待 {interval} 秒后再次检查...")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Batch 批量监控")
    parser.add_argument("batch_ids", nargs="+", help="Batch IDs")
    parser.add_argument("--watch", "-w", action="store_true", help="持续监控")
    parser.add_argument("--interval", "-i", default="10m", help="检查间隔 (如 10m, 5m, 30s)，默认 10 分钟")
    parser.add_argument("--check", "-c", action="store_true", help="仅检查完成状态")

    args = parser.parse_args()
    orbit_path = get_orbit_path()

    interval_str = args.interval
    try:
        if interval_str.endswith("m"):
            interval = int(interval_str[:-1]) * 60
        elif interval_str.endswith("s"):
            interval = int(interval_str[:-1])
        else:
            interval = int(interval_str)
    except ValueError:
        parser.error(f"无法解析 interval: {interval_str!r}，格式示例: 5m, 30s, 300")

    if args.watch:
        monitor_watch(args.batch_ids, interval, orbit_path)
    elif args.check:
        results = monitor_once(args.batch_ids, orbit_path)
        all_finished = all(
            r.get("progress", {}).get("batchStatus") in ["finished", "failed"]
            for r in results.values()
        )
        sys.exit(0 if all_finished else 1)
    else:
        monitor_once(args.batch_ids, orbit_path)


if __name__ == "__main__":
    main()
