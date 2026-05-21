# Benchmark 数据质量验证

构造完 benchmark 后，必须通过以下验证才能投入使用。两个硬门槛缺一不可。

---

## 硬门槛 1：Badcase 复现率 ≥ 1/10

**含义**：用当前模型跑同一个 query 10 次，至少 1 次能复现原始 badcase 中的问题。

**为什么需要**：如果一个 badcase 完全不可复现，说明它可能是偶发的、已被修复的、或环境依赖的，不适合作为 benchmark。

### 验证方法

**Chatty 链路：**

```bash

# 对每条 badcase query 跑 10 次
# 创建一个重复 10 次的 CSV
python -c "
import csv, sys
with open('bmk/to_validate.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
with open('bmk/to_validate_x10.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    for row in rows:
        for _ in range(10):
            writer.writerow(row)
"

# 批量跑
python scripts/rollout-batch_chatty.py @bmk/to_validate_x10.csv \
  --url https://chatty.dev.AI_Platform.team -o bmk/validate_x10 -j 10

# 用 judge 打分
python scripts/judge/judge.py bmk/validate_x10 \
  --bmk bmk/to_validate.csv --label validate --prompt simple -j 40
```

**Platform 链路：**

在 Platform 中对同一 dataset 跑多次 Rollout，或利用 `num_reps` 参数。

### 判定标准

对每条 badcase：
- 统计 10 次中得分 ≤ 0.5（simple 模式）或不达标的次数
- **复现次数 ≥ 1 → PASS**
- **复现次数 = 0 → FAIL，移除该条**

汇总报告：
```
BMK 验证报告 - 复现率
总条数: 50
通过: 42 (84%)
未通过: 8 (16%) → 建议移除
平均复现率: 3.2/10
```

---

## 硬门槛 2：Frontier vs Eval Model 差距 ≥ 10 分

**含义**：用 frontier model（如 GPT-5、Claude Opus）和待评测模型分别跑 benchmark，平均分差距 ≥ 10 分（百分制）。

**为什么需要**：如果 frontier model 也拿不到高分，说明 benchmark 本身的评判标准有问题（太严、不合理、或描述不清）。如果两者分数接近，说明 benchmark 区分度不够，无法有效检测体验差异。

### 验证方法

**Chatty 链路：**

```bash

# Frontier model（用Internal_AI_Service API 调外部模型）
# 需要在 batch_chatty.py 之外单独调用Internal_AI_Service API
# 或用 Platform 链路对比

# Eval model（当前 AI_Platform 模型）
python scripts/rollout-batch_chatty.py @bmk/dataset.csv \
  --url https://chatty.dev.AI_Platform.team -o bmk/eval_model -j 10

# Judge 两组结果
python scripts/judge/judge.py bmk/frontier_model bmk/eval_model \
  --bmk bmk/dataset.csv --label frontier eval --prompt simple -j 40
```

**Platform 链路：**

```bash
# 分别用两个模型跑 Rollout
# Model A: frontier (如 claude-opus-4)
# Model B: eval (如 AI_Platform-k2.5)
# Platform Judge 做 GSB 对比，或分别打分后算差值
```

### 判定标准

| 指标 | 计算方式 | 阈值 |
|------|----------|------|
| 分差 | `avg(frontier_score) - avg(eval_score)` | ≥ 10 分（百分制） |
| Frontier 基线 | `avg(frontier_score)` | ≥ 70 分（说明标准合理） |
| GSB win rate | frontier Better 的比例 | ≥ 60% |

**结果解读：**

| 情况 | 说明 | 行动 |
|------|------|------|
| 差距 ≥ 10 且 frontier ≥ 70 |  BMK 有效 | 可投入使用 |
| 差距 ≥ 10 但 frontier < 70 | ️ 标准过严 | 放宽 rubric 或降低难度 |
| 差距 < 10 且 frontier ≥ 90 | ️ 区分度不够 | 增加难题比例或加严 rubric |
| 差距 < 10 且 frontier < 70 |  BMK 有问题 | 重新审视评判标准 |

---

## 补充验证（推荐但非必须）

### Judge 一致性检验

同一组结果用 Judge 跑两次，检查打分一致性：

```python
# 两次 judge 结果对比
import pandas as pd

df1 = pd.read_excel('judge/result/run1.xlsx')
df2 = pd.read_excel('judge/result/run2.xlsx')

# 计算一致率
agreement = (df1['score'] == df2['score']).mean()
print(f"Judge 一致率: {agreement:.1%}")
# 建议 ≥ 80%
```

### 数据集多样性检查

参考 Anthropic Bloom 的 diversity meta-judgment：
- 检查 query 的语义多样性（不要都是同一种问法）
- 检查场景覆盖度（每个子类型至少 5 条）
- 检查难度分布是否合理

### 评测本身的质量评分

参考 Bloom 的 additional_qualities：
- **unrealism**：场景是否过于人造？
- **evaluation-invalidity**：评判标准是否真的合理？
- **elicitation-difficulty**：是否太容易/太难触发问题？

---

## 验证流程总结

```
构造完数据集
    ↓
[门槛 1] 复现率 ≥ 1/10
    ↓ PASS
[门槛 2] frontier 差距 ≥ 10 分
    ↓ PASS
[推荐] Judge 一致性 ≥ 80%
    ↓ PASS
 BMK 可投入使用
```

任何一个硬门槛未通过 → 回到 badcase-to-bmk 阶段调整数据。
