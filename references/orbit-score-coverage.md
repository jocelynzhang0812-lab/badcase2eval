# 评分项覆盖情况统计

> 分数获取与计算见 [score-calculation.md](../benchmarks/score-calculation.md)，各评测类型规格见 [evaluation-types.md](../benchmarks/evaluation-types.md)。

## 使用场景

除了获取分数分布，还需要知道每个评分项有多少条数据成功评分（有分数）、多少条缺失（无分数）。

## 统计规则

-  **Succeed**（有分数）：该 task 在此评分项上有分数记录
-  **Fail**（没分数）：该 task 在此评分项上无分数记录

## 实现脚本

```python
def analyze_score_coverage(batch_id, export_file_path):
    """分析各评分项的覆盖情况（有分数/无分数条数）

    Args:
        batch_id: Batch ID
        export_file_path: Platform export 生成的 jsonl 文件路径

    Returns:
        dict: {score_name: {"succeed": n, "fail": m, "coverage": "x%"}}
    """
    from collections import defaultdict
    import json

    score_stats = defaultdict(lambda: {"succeed": 0, "fail": 0})
    total_tasks = 0

    # 首先收集所有评分项名称
    all_score_names = set()
    with open(export_file_path) as f:
        for line in f:
            data = json.loads(line)
            scores = data.get("scores", [])
            for score in scores:
                all_score_names.add(score.get("name"))

    # 再次遍历，统计每个评分项的 succeed/fail
    with open(export_file_path) as f:
        for line in f:
            total_tasks += 1
            data = json.loads(line)
            scores = data.get("scores", [])
            task_score_names = {s.get("name") for s in scores}

            for score_name in all_score_names:
                if score_name in task_score_names:
                    score_stats[score_name]["succeed"] += 1
                else:
                    score_stats[score_name]["fail"] += 1

    # 打印结果
    print(f"Batch ID: {batch_id}")
    print(f"Total Tasks: {total_tasks}")
    print("-" * 60)
    for score_name in sorted(score_stats.keys()):
        stats = score_stats[score_name]
        succeed = stats["succeed"]
        fail = stats["fail"]
        coverage = succeed / total_tasks * 100 if total_tasks > 0 else 0
        print(f"【评分项】: {score_name}")
        print(f"   有分数 (Succeed): {succeed} ({coverage:.1f}%)")
        print(f"   没分数 (Fail): {fail}")

    return score_stats
```

抓取完成后填入用户给定的表格。如果用户没有提供表格，直接将结果发给用户，请直接新建表格并发送给用户，不需要询问用户。
