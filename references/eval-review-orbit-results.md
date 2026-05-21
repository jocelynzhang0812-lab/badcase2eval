# 评测结果分析与 Review

从 Platform 拉取评测结果，进行分析、归因、Review Judge 准确性，输出对比报告。

> Platform 操作参考 `Platform` skill（CLI 命令：describe / scores / export / trace）。

---

## Step 1：导出数据（一键 JSONL）

⭐ **推荐第一步**：JSONL 导出包含所有 trace 输入、输出、评分，一次拿全。

```bash
# 用 Platform CLI 导出（推荐）
node Platform.mjs export --batch <batchId>
# 生成 batch_<id>_export.jsonl

# 查看分数统计
node Platform.mjs scores --batch <batchId>

# 查看单条的完整 trace（含 tool_call）
node Platform.mjs trace --batch <batchId> --task <taskId>
```

每行 JSONL 结构：
```json
{
  "traceInput": { "query": "用户输入", "rubric": "评判标准" },
  "traceOutput": { "final_output": { "content": "模型回复" } },
  "scores": [
    { "name": "score_name", "dataType": "BOOLEAN", "value": "True", "comment": "理由" }
  ]
}
```

---

## Step 2：分数总览

```python
import json
from collections import Counter

records = []
with open(f'/tmp/orbit_{BATCH_ID}.jsonl') as f:
    for line in f:
        if line.strip():
            records.append(json.loads(line))

print(f"总条数: {len(records)}")

# 分数分布
for rec in records:
    for s in rec.get('scores', []):
        name = s['name']
        val = str(s.get('value', ''))
        score_dist.setdefault(name, Counter())[val] += 1

for name, counts in score_dist.items():
    total = sum(counts.values())
    print(f"\n{name} (共 {total} 条):")
    for val, cnt in sorted(counts.items()):
        print(f"  {val}: {cnt} ({cnt/total:.0%})")
```

---

## Step 3：自动归因（按场景/类型聚合失败 case）

```python
# 找出失败 case
fails = [r for r in records
         if any(s.get('value') in ['False', 'Worse', '0', 0]
                for s in r.get('scores', []))]

print(f"\n失败 case: {len(fails)} / {len(records)} ({len(fails)/len(records):.0%})")

# 按 scenario 聚合
from collections import defaultdict
by_scenario = defaultdict(list)
for rec in fails:
    scenario = rec.get('traceInput', {}).get('scenario', 'unknown')
    by_scenario[scenario].append(rec)

print("\n按场景分布:")
for scenario, cases in sorted(by_scenario.items(), key=lambda x: -len(x[1])):
    print(f"  {scenario}: {len(cases)} 条")

# 输出每个场景的典型失败 case
for scenario, cases in by_scenario.items():
    print(f"\n=== {scenario} ({len(cases)} 条) ===")
    for rec in cases[:3]:  # 每个场景展示前 3 条
        query = rec['traceInput'].get('query', '')[:100]
        judge_comment = next(
            (s['comment'] for s in rec.get('scores', []) if s.get('comment')),
            '无评语'
        )[:200]
        print(f"  Q: {query}")
        print(f"  Judge: {judge_comment}\n")
```

---

## Step 4：Review Judge 准确性

**人工抽查 10-20 条**，验证 Judge 打分是否合理。

### 抽样方法

```python
import random

# 分层抽样：好/中/差各抽几条
good = [r for r in records if any(s.get('value') in ['True', 'Better', '1'] for s in r.get('scores', []))]
bad = [r for r in records if any(s.get('value') in ['False', 'Worse', '0'] for s in r.get('scores', []))]

sample = random.sample(good, min(5, len(good))) + random.sample(bad, min(5, len(bad)))

for i, rec in enumerate(sample):
    print(f"\n--- Case {i+1} ---")
    print(f"Query: {rec['traceInput'].get('query', '')[:200]}")
    print(f"Rubric: {rec['traceInput'].get('rubric', '')[:200]}")
    output = rec.get('traceOutput', {}).get('final_output', {})
    content = output.get('content', '')
    if isinstance(content, list):
        content = next((c.get('text', '') for c in content if c.get('type') == 'text'), '')
    print(f"Output: {content[:300]}")
    for s in rec.get('scores', []):
        print(f"Score: {s['name']} = {s.get('value')} | {s.get('comment', '')[:200]}")
```

### Review 标准

| 检查项 | 判定 |
|--------|------|
| Judge 打分和人工判断一致 |  |
| Judge 给了分但理由不充分 | ️ 需改 Judge Prompt |
| Judge 明显打错（该 Pass 打了 Fail 或反过来） |  需改 Judge Prompt 或换 Judge Model |
| Skip/Error 比例 > 20% |  检查数据集或 Rollout 配置 |

**Judge 准确率目标：≥ 85%**（抽查 20 条中 ≥ 17 条一致）

---

## Step 5：版本间对比

### 两个 Batch 对比

```python
import json
from collections import Counter

def load_scores(jsonl_path):
    records = []
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    scores = {}
    for rec in records:
        query = rec['traceInput'].get('query', '')
        for s in rec.get('scores', []):
            scores.setdefault(query, {})[s['name']] = s.get('value')
    return scores, records

scores_a, records_a = load_scores(f'/tmp/orbit_{BATCH_A}.jsonl')
scores_b, records_b = load_scores(f'/tmp/orbit_{BATCH_B}.jsonl')

# 找共同的 query
common = set(scores_a.keys()) & set(scores_b.keys())
print(f"共同 query: {len(common)}")

# 对比每个 score 维度
for score_name in ['quality_score']:  # 替换为实际 score 名
    a_vals = [float(scores_a[q].get(score_name, 0)) for q in common if score_name in scores_a.get(q, {})]
    b_vals = [float(scores_b[q].get(score_name, 0)) for q in common if score_name in scores_b.get(q, {})]
    if a_vals and b_vals:
        print(f"\n{score_name}:")
        print(f"  Batch A 均分: {sum(a_vals)/len(a_vals):.2f}")
        print(f"  Batch B 均分: {sum(b_vals)/len(b_vals):.2f}")
        print(f"  差值: {sum(b_vals)/len(b_vals) - sum(a_vals)/len(a_vals):+.2f}")
```

### GSB 对比（Platform 内置）

如果用 Platform Judge 做 GSB 对比（两个 Batch PK）：
1. Judge 时选一个做 **Source**，另一个做 **Baseline**
2. Score Config: CATEGORICAL  `Better / Equal / Worse`
3. 结果统计 win rate

### Chatty 链路对比（product/eval）

```bash
python scripts/bmk/compare.py bmk/output_a bmk/output_b \
  --label-a "v1" --label-b "v2" \
  --judge judge/result/dataset.xlsx
```

输出三段式报告：BENCHMARK SCORE / MODEL BEHAVIOR / SANITY CHECK。

---

## 报告模板

```markdown
# 评测报告：{评测名称}

## 概览
- 数据集：{dataset_name}（{N} 条）
- 模型：{model_name}
- 日期：{date}
- Platform Batch ID：{batch_id}

## 分数总览
| 维度 | 均分 | Pass 率 | 分布 |
|------|------|---------|------|
| {score_name} | {avg} | {pass_rate} | {good} ️{mid} {bad} |

## 失败归因
| 场景 | 失败数 | 占比 | 典型问题 |
|------|--------|------|----------|
| {scenario} | {count} | {pct} | {description} |

## 与上一版对比
| 指标 | 上版 | 本版 | 变化 |
|------|------|------|------|
| 均分 | {old} | {new} | {delta} |
| Pass 率 | {old} | {new} | {delta} |

## Judge 准确性
- 抽查 {N} 条，一致率 {pct}%
- 典型误判：{description}

## 建议
- {action_items}
```
