# 从零创建 Benchmark

**什么都没有？按这个流程一步步来。**

每一步完成后会产出一个东西，下一步用上一步的产出。跳过任何一步都会导致后面出问题。

---

## Step 1：定义评测目标

**产出：明确要评什么、用什么标准判断好坏**

️ 问用户：
1. "你要评测什么场景？"（搜索质量 / 回复质量 / 工具使用 / 安全 / ...）
2. "有没有对应的价值观文档？"

→ 用 **kitty-feishu** skill 打开价值观文档目录：
https://internal-docs.company.com/wiki/SwnvwNW9ViXTMLkOzmacqbtqnFe

→ 找到对应场景的价值观文档，通读一遍，提取关键评判维度。

**完成标志**：能回答"我要评 XXX 场景，关键评判维度是 A、B、C"。

---

## Step 2：设计评判标准

**产出：每道题的打分点（rubric / ground_truth）**

评判标准有两种写法：

### 通用 rubric（适合主观评测）

每道题一个文字描述的打分点，告诉 judge "什么样的回答是好的"：

```
rubric: "回复应包含3条以上近期新闻，搜索词应含时间限定词，引用需标注来源"
```

### 结构化 ground_truth（适合有标准答案的评测）

每道题一个结构化的期望输出，告诉 judge 模型应该做什么：

```json
{
  "ground_truth": [
    {"tool": "web_search", "params": {"query": "AI监管 最新"}},
    {"expected_in_response": "2026年"}
  ]
}
```

️ 问用户：
1. "你的场景适合哪种打分标准？"
2. "能给一两个例子吗？"（用例子确认标准的粒度是否合适）

**完成标志**：有 3-5 个示例题目 + 对应的打分标准。

---

## Step 3：设计 Judge Prompt

**产出：一个可用的 Judge Prompt（保存在 Langfuse 上）**

→ 先读 [eval-judge-modes.md](eval-judge-modes.md) 确定打分模式：

| 你的情况 | 用哪种模式 |
|---------|-----------|
| 只有一个模型 + 有打分点 | 绝对打分（NUMERIC） |
| 两个模型 PK | GSB 对比（CATEGORICAL） |
| 两个模型 + 有打分点 | 打分+对比（融合） 推荐 |

→ 从 eval-judge-modes.md 选对应模式的 System Prompt 模板，根据 Step 2 的打分标准修改。

**关键检查：**
- prompt 里的 `{{字段名}}` 和你的数据集字段对得上吗？
- 输出格式是 JSON 吗？（方便自动解析）
- 有没有说清楚评分规则？（满分条件、部分满足条件、零分条件）

→ 在 Langfuse 上创建 Prompt：
- 类型选 **Text**（不是 Chat！）
- 勾上 **production** label
- 命名规范：`<你的名字>/<场景>-judge`（如 `xjf/search-quality-judge`）

️ 问用户确认 prompt 内容。

**完成标志**：Langfuse 上有一个 production 状态的 Judge Prompt。

---

## Step 4：选评测参数

**产出：一组确定的评测配置（preset + model + configId + thinking）**

→ 读 [rollout-Platform-guide.md](rollout-Platform-guide.md) 的 Preset 章节。

### 快速决策：

| 问题 | 选择 |
|------|------|
| 评测 AI_Platform？ | preset: `kimi_chat`（搜索场景）或 `kimi_agent`（Agent 场景） |
| 评测外部模型？ | `presets` 命令查询当前可用的外部模型 preset |
| 自部署模型？ | preset: `self_deployed`，需要 model URL |
| 要不要 thinking？ | 默认开（AI_Platform preset 自带），不要就加 `--thinking 0` |
| 用什么 Judge？ | `presets --type orbit_judge` 查询可用 judge preset |
| judgePattern？ | `agent`（需读附件/执行代码）/ `llm`（标准文本打分，快且便宜）/ `script`（规则化评测） |
| judgeMode？ | `response_only`（默认，评回复质量）/ `all_trace_without_sp`（评工具调用/搜索策略）/ `all_trace`（调试用） |

### Score Config：

需要在 Platform UI 上创建或选择已有的 Score Config：
- NUMERIC（0-10）→ 绝对打分
- CATEGORICAL（Better/Equal/Worse）→ GSB 对比
- BOOLEAN（True/False）→ 底线检查

→ 读 [evaluation-types.md](../benchmarks/evaluation-types.md#score-config-速查) 查已有的 Score Config。

️ 列出所有默认值，问用户哪些要改。

**完成标志**：能填出这张表：

| 参数 | 值 |
|------|-----|
| Runner Preset | ? |
| Model | ? |
| Prompt | ? |
| ConfigId | ? |
| Thinking | ? |
| Judge Preset | ? |
| Judge Prompt | ? |
| Score Configs | ? |
| judgePattern | agent / llm / script |
| judgeMode | response_only / all_trace_without_sp / all_trace |

---

## Step 5：构造初始数据集

**产出：一个上传到 Platform 的数据集（≥ 20 条）**

### 数据从哪来？

| 来源 | 适合 | 怎么做 |
|------|------|--------|
| **已有 badcase** | 已经收集了一些问题 case | → 读 [data-badcase-flow.md](data-badcase-flow.md) + [data-badcase-to-bmk.md](data-badcase-to-bmk.md) |
| **[Internal Docs Platform]表格** | 有人维护了一个评测题目表 | → `data-bitable_to_orbit.py` |
| **CSV 文件** | 有现成的题目 CSV | → `data-csv_to_orbit.py` |
| **LLM 生成** | 什么都没有，从零构造 | → `data-bloom_generate.py`（生成场景）→ `data-bloom_rollout.py`（多轮探测） |
| **线上反馈** | 从用户反馈里找 case | → `data-query_feedback.py` 查反馈 → `data-get_message.py` 拉 trace |

### 数据格式要求：

- 每条至少有 `query` 字段
- 如果有打分标准，放 `rubric` 或 `ground_truth` 字段
- Judge Prompt 里 `{{}}` 引用的字段必须放 **Input**，只用来筛选的放 **Metadata**
- 详见 [data-csv-to-Platform.md](data-csv-to-Platform.md)

### 上传 + 校验：

```
Platform CLI upload --file dataset.jsonl --dataset "my-benchmark-v1" --dry-run
→ 确认后执行
→ verify_upload.py 自动校验
```

**完成标志**：Platform 上有一个数据集，verify_upload 校验通过。

---

## Step 6：试跑验证

**产出：确认数据集和 judge prompt 都能正常工作**

### 小规模试跑（5-10 条）：

```
Platform CLI run --preset <preset> --dataset <dataset> --items <5条的id> --dry-run
→ 确认后执行
→ 等完成
→ Platform CLI describe --batch <id> 查进度
```

### 检查 Judge 打分：

```
Platform CLI scores --batch <id>
→ 看分数分布是否合理
→ 导出几条看 judge 的 reason，打分有没有道理
```

### 常见问题：

| 问题 | 原因 | 解决 |
|------|------|------|
| 全是满分 | rubric 太宽松 | 加更细的打分标准 |
| 全是零分 | rubric 太严格或和 query 不匹配 | 检查 rubric 是否合理 |
| judge reason 不靠谱 | judge prompt 不清晰 | 修改 prompt，在 Judge Playground 调试 |
| task 失败 | 参数配置问题 | `Platform CLI inspect` 诊断 |

️ 试跑结果展示给用户，确认是否满意。不满意就回到 Step 2/3/4 调整。

**完成标志**：试跑结果合理，judge 打分有道理。

---

## Step 7：正式跑 + 持续迭代

试跑通过后，全量跑评测：

```
Platform CLI run --preset <preset> --dataset <dataset> --dry-run
→ 确认后执行
→ 完成后看 scores
→ 分析结果，读 eval-review-Platform-results.md
```

### 持续迭代：

- 发现新 badcase → 加入数据集（回到 Step 5）
- judge prompt 不准 → 调整 prompt（回到 Step 3）
- 新模型版本 → 重跑评测，对比分数
- 数据集过时 → 更新 case，检查时效性

---

## 检查清单

开始正式评测前，确认以下全部就绪：

- [ ] 评测目标明确（场景 + 价值观维度）
- [ ] 打分标准写好（rubric / ground_truth）
- [ ] Judge Prompt 创建并上 production
- [ ] Score Config 创建或选好
- [ ] 数据集上传并校验通过
- [ ] 试跑结果合理
- [ ] 评测参数确认（填好上面那张表，含 judgePattern + judgeMode）
