# 运行前预检（Pre-flight Check）

dry-run 通过后、正式执行前，**必须**完成以下四步预检。

> 确认清单模板见 [Platform-interaction-principles.md](../references/Platform-interaction-principles.md#运行前确认清单模板)，各评测类型规格见 [evaluation-types.md](evaluation-types.md)。

---

## Step 0: AKSK 检查

确认 Platform 密钥配置完整，缺少任何一项都会导致 run/judge 失败。

```bash
python scripts/rollout-setup_aksk.py --check
```

### 必需的密钥

| 密钥 | 用途 |
|------|------|
| `AuthGateway_ACCESS_TOKEN` | Platform API 认证 |
| `OPENAI_API_KEY` | 外部模型 judge（如 GPT） |
| `ANTHROPIC_API_KEY` | 外部模型 judge（如 Claude） |

### 判定规则

| 状态 | 操作 |
|------|------|
| 所有密钥已配置 |  继续下一步 |
| 缺少任何密钥 |  **停止**，提醒用户运行 `python scripts/rollout-setup_aksk.py` 配置后再继续 |

---

## Step 1: 模型健康检查

检查 **rollout 模型** 和 **judge 模型** 在Internal_AI_Service平台的节点状态。

```bash
# 检查 rollout 模型
node Platform.mjs model-health --model <rollout-model-name>

# 检查 judge 模型（根据评测方向确定）
node Platform.mjs model-health --model <judge-model-name>
```

### 判定规则

| health 值 | 含义 | 操作 |
|-----------|------|------|
| `healthy` (health=0) | 节点正常 |  继续 |
| `abnormal` (health≠0) | 节点异常 | ️ 告知用户，建议等待或换模型 |
| `disabled=true` | 已下线 |  **停止**，提示用户模型不可用 |

### Judge 模型的确定方式

Judge 模型**不应硬编码**，通过以下方式获取：

1. **优先**：查看同一 Dataset 的历史 batch`node Platform.mjs dataset-runs --dataset <name>` 找到已完成的 batch ID，然后 `describe --batch <batchId>` 查看其 auto-judge 配置中的 judge 模型
2. **备选**：根据下方成本估算表中的主要 Judge 模型列，按评测方向确定常用 judge 模型
3. 对确定的所有 judge 模型执行健康检查：`node Platform.mjs model-health --model <judge-model>`

>  `model-health --model <keyword>` 支持模糊匹配，如 `--model sonnet` 会匹配所有 Sonnet 变体。

---

## Step 2: 成本估算

根据评测方向，估算本次任务的 judge 成本。

> Rollout 使用内部 AI_Platform 模型时不产生Internal_AI_Service API 费用，以下成本均为 **judge 费用**。
> 成本明细来源：[[Internal Docs Platform]花销参考表](https://internal-docs.company.com/wiki/CChqwIQWAiiJBjkswagcIEYhnfb?sheet=4e5997)
> 
> ️ **Last updated: 2026-04**｜模型换代后单价可能变化较大，请定期对照[Internal Docs Platform]花销表更新。

### 全量评测单次成本参考

> ℹ️ 以下数据为 2026-04 快照，实际成本以[[Internal Docs Platform]花销参考表](https://internal-docs.company.com/wiki/CChqwIQWAiiJBjkswagcIEYhnfb?sheet=4e5997)为准。

| 评测方向 | 数据集数 | 总 tasks | 主要 Judge 模型 | 单次成本估算 (¥) |
|---------|---------|---------|----------------|-----------------|
| **Text** | 18 | ~1,342 | sonnet / gemini | **~1,469** |
| **Vision** | 15 | ~1,314 | gemini / sonnet | **~1,464** |
| **Withtools** | 10 | ~408 | opus-4-6（最贵） | **~1,606** |
| **Arena** | 2 | ~250 | opus / sonnet | **~306** |
| **底线 (Dixian)** | 3×batch | ~624 | gemini-judgeonly | **~242** |
| **专项** | 8 | ~310 | 混合 | **~130** |
| **全量总计** | 56 | ~4,248 |  | **~¥5,216** |

### 估算方法

1. 从 dry-run 输出中获取 **数据集名称** 和 **items 数量**
2. 根据评测方向查上表的单 task 均价：
   - Text: ~¥1.09/task
   - Vision: ~¥1.11/task
   - Withtools: ~¥3.93/task（opus judge，最贵）
   - Arena: ~¥1.23/task
   - 底线: ~¥0.39/task
   - 专项: ~¥0.42/task
3. **预估成本 = items 数量 × 单 task 均价**

> ️ Withtools 方向最贵（使用 opus judge + 双维度评分），约为 Text/Vision 的 3.5 倍。

### 单数据集成本估算

如果只跑部分数据集，按以下粒度估算：

```
预估成本(¥) ≈ task数 × 对应方向均价/task
```

示例：跑 80 tasks 的 Withtools 搜索数据集 → 80 × 3.93 ≈ ¥314

---

## Step 3: 余额检查

```bash
node Platform.mjs balance
```

输出示例：
```json
{ "used": 52311.72, "quota": 55000, "remaining": 2688.28 }
```

> ℹ️ balance 返回的 `remaining`、`used`、`quota` 单位均为 **人民币 (¥)**，与成本估算单位一致，**无需汇率换算**。

### 判定规则

| 条件 | 操作 |
|------|------|
| 剩余余额 > 预估成本 × 1.2 |  余额充足（留 20% 缓冲） |
| 剩余余额 > 预估成本 | ️ 余额紧张，提醒用户注意 |
| 剩余余额 < 预估成本 |  **余额不足**，必须告知用户并建议充值或缩减范围 |

### 余额不足时的建议

1. **缩减数据集范围**：用 `--items` 只跑部分 items
2. **换便宜的 Judge 模型**：如 gemini 替代 opus
3. **联系管理员充值**：Internal_AI_Service平台 → 账户管理
4. **分批次跑**：先跑高优先级数据集

---

## 完整预检流程示例

```
用户：确认，开始跑 text 方向

Kitty：
 运行前预检：

0️⃣ AKSK 检查
    AuthGateway_ACCESS_TOKEN: 已配置
    OPENAI_API_KEY: 已配置
    ANTHROPIC_API_KEY: 已配置

1️⃣ 模型健康检查
    rollout 模型 AI_Platform-k2.5: healthy
    judge 模型 <judge-model-1>: healthy
    judge 模型 <judge-model-2>: healthy

2️⃣ 成本估算
   Text 方向全量（18 数据集，1,342 tasks）
   预估 judge 成本：~¥1,469

3️⃣ 余额检查
   当前余额：¥2,688
    余额充足（预估成本占余额 8%）

所有预检通过 ，开始正式创建 batch...
```

### 余额不足示例

```
Kitty：
 运行前预检：

0️⃣ AKSK 检查
    所有密钥已配置

1️⃣ 模型健康检查
    rollout 模型: healthy
    judge 模型: healthy

2️⃣ 成本估算
   Withtools 方向全量（10 数据集，408 tasks）
   预估 judge 成本：~¥1,606

3️⃣ 余额检查
   当前余额：¥150
    余额不足！预估成本 ¥1,606 > 可用余额 ¥150

建议：
- 缩减范围：只跑高优先级数据集（如「复杂搜索_text」80 tasks ≈ ¥314）
- 或联系管理员充值后再继续

请问如何处理？
```

---

## See also

- [Platform-interaction-principles.md](../references/Platform-interaction-principles.md)  确认清单模板
- [evaluation-types.md](evaluation-types.md)  各方向 Judge 配置
- [score-calculation.md](score-calculation.md)  算分 pipeline
- [花销参考表（[Internal Docs Platform]）](https://internal-docs.company.com/wiki/CChqwIQWAiiJBjkswagcIEYhnfb?sheet=4e5997)  最新成本明细
