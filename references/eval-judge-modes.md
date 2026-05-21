# Judge 打分模式指南

三种 Judge 打分模式，按需选择。已有 Chatty 链路的可执行 prompt 在 `scripts/judge/judge_prompt/prompt.py`。

---

## 从零设计 Judge Prompt

如果还没有 Judge Prompt，按这 4 步走：

**1️⃣ 确定打分粒度**

| 问自己 | 选择 |
|---------|------|
| 每道题只需要一个总分？ | 单维度（一个 score） |
| 需要按多个方面分别打分？ | 多维度（多个 score config） |

**2️⃣ 写打分规则**

好的打分规则要包含：
- 满分条件：什么样的回答得满分？
- 零分条件：什么样的回答得零分？
- 中间地带：部分满足怎么算？
- 拒答处理：模型拒绝回答算几分？

示例：
```
评分规则：
- 1 分: 所有标准全部满足
- 0.5 分: 部分标准满足，或某条部分满足
- 0 分: 没有标准被满足，或模型拒绝回答
```

**3️⃣ 选模式（见下方速查表）**

**4️⃣ 在 Langfuse 上创建**
- 类型选 **Text**（不是 Chat！）
- 勾 **production** label
- 命名：`<你的名字>/<场景>-judge`
- 用 Judge Playground 试跑 1-2 条，确认打分合理

---

## 速查表

| 模式 | Score Config 类型 | 输出 | 适合场景 | 前提 |
|------|------------------|------|---------|------|
| **绝对打分** | NUMERIC | 分数 + 逐条理由 | 单模型评测、有明确打分点 | 每道题有 rubric/ground_truth |
| **GSB 对比** | CATEGORICAL | Better/Equal/Worse + 理由 | 两个模型 PK | 有两组回复（arena 或两个 batch） |
| **打分+对比** | CATEGORICAL + NUMERIC | 两边各一个分数 + GSB 结论 | 有打分点 + 想做模型对比 | 每道题有 rubric + 有两组回复 |

---

## Prompt 设计原则

参考 `scripts/judge/judge_prompt/prompt.py` 的成熟实践，所有模板统一遵循：

1. **逐条独立评判**：先单独评每条标准，再汇总。避免一条不满足就全盘否定
2. **结构化 JSON 输出**：明确字段和格式，方便自动解析
3. **只看实质内容**：忽略排版、引用标记、客套话，聚焦答案本身
4. **时效性检查**：如果标准涉及"最新数据"，检查回复是否确实反映了近期信息
5. **拒答兜底**：模型回复如果是拒绝/"我不知道"，直接 0 分

---

## 模式 1：绝对打分（NUMERIC）

**一个模型，按标准逐条打分。**

### 什么时候用

- 只跑了一个模型（单 batch）
- 想知道"这个模型在这道题上得几分"
- 有明确的 rubric / ground_truth / 打分点

### ️ 前提检查

- Dataset 里必须有打分点字段（`rubric` 或 `ground_truth`）
- Judge Prompt 里必须用 `{{}}` 引用该字段

### System Prompt

```
你是一个严格的评测裁判。你会收到用户问题、评判标准和模型回复。你的任务是判断模型回复是否满足所有评判标准。

规则：
1. 逐条独立评判每个标准，然后给出总分。
2. 只有回复明确、无歧义地满足标准时，该条才算"通过"。
3. 忽略排版、引用标记和客套话只看实质内容。
4. 如果标准涉及时效性信息，检查回复是否确实包含最新/近期数据，而非过时事实。

评分：
- 1   = 所有标准全部满足
- 0.5 = 部分标准满足，或某条标准部分满足
- 0   = 没有标准被满足，或模型拒绝回答

输出 JSON，字段如下：
- "details": 数组，每条标准的评判结果 [{"criterion": "标准内容", "met": true/false, "comment": "理由"}]
- "score": 1 / 0.5 / 0
- "reason": 一句话总结
```

### User Prompt

```
用户问题：
{{query}}

评判标准：
{{ground_truth}}

模型回复：
{{response}}

请按评判标准逐条评估模型回复。
```

### Platform 配置

- Score Config 类型：**NUMERIC**（min=0, max=1）
- judgeMode：`response_only`（只看回复）或 `all_trace_without_sp`（看完整 trace，适合评工具调用）
- Langfuse Prompt 类型：**Text**（不是 Chat）

---

## 模式 2：GSB 对比（CATEGORICAL）

**两个模型的回复放在一起，judge 判断谁更好。**

### 什么时候用

- 有两个模型（新旧版本 / A/B 实验 / 竞品对比）
- 想知道"哪个更好"而不只是"各自几分"
- 可以没有打分点（judge 用通用标准判断）

### ️ 前提检查

**必须有两组回复。** 没有两组回复就不要用 GSB：
-  `arena` 命令：同一个 dataset 跑两个模型，自动对比
-  分别 `run` 两个 batch，再用 `judge` 对比
-  只有一个 batch → 不要用 GSB，用 NUMERIC

### System Prompt（无打分点）

```
你是一个评测裁判。你会收到用户问题和两个模型的回复（A 和 B）。你的任务是判断哪个回复更好。

规则：
1. 从信息准确性、完整性、是否切题、表达清晰度等维度综合判断。
2. 忽略排版和客套话，只看实质内容。
3. 如果两个回复质量接近、无法明确区分，判 Equal。
4. 如果其中一个是拒绝回答而另一个正常回答，正常回答的一方更好。

输出 JSON：
- "choice": "Better" / "Equal" / "Worse"（Better = A 更好，Worse = A 更差）
- "reason": 简要说明判断依据
```

### System Prompt（有打分点）

```
你是一个评测裁判。你会收到用户问题、评判标准和两个模型的回复（A 和 B）。你的任务是基于评判标准判断哪个回复更好。

规则：
1. 逐条对照评判标准，分别检查 A 和 B 各满足了哪些。
2. 满足更多标准的一方更好。
3. 忽略排版和客套话，只看实质内容。
4. 如果两个回复在标准满足度上接近，判 Equal。

输出 JSON：
- "summary_a": "A 满足了标准 1/3，缺失标准 2"
- "summary_b": "B 满足了标准 1/2/3"
- "choice": "Better" / "Equal" / "Worse"
- "reason": 简要总结
```

### User Prompt

```
用户问题：
{{query}}

评判标准：（如有）
{{ground_truth}}

回复 A：
{{response_a}}

回复 B：
{{response_b}}

请判断哪个回复更好。
```

### Platform 配置

- Score Config 类型：**CATEGORICAL**（类别：Better / Equal / Worse）
- 用 `arena` 命令，或两个 batch + `judge`
- judgeMode：`response_only`
- Langfuse Prompt 类型：**Text**

---

## 模式 3：打分+对比（推荐）

**先按打分点给两边各打一个分，再基于分数给出 GSB 结论。一次调用，三个结果。**

### 什么时候用

- 有两个模型 **且** 每道题有打分点
- 想同时知道"各自几分"和"谁更好"
- 希望 GSB 结论有分数支撑，不是凭感觉

### 为什么比分两步跑好

| | 分两步（先 NUMERIC 再 GSB） | 一步融合 |
|---|---|---|
| 公平性 | 分开打分，标准可能漂移 | 同时看两边，对比更公平 |
| 成本 | 两次 judge 调用 | 一次调用 |
| 一致性 | 可能出现"A分高但GSB说B好" | 分数和GSB内在一致 |

### System Prompt

```
你是一个评测裁判。你会收到用户问题、得分规则和两个模型的回复（A 和 B）。你的任务是按规则分别打分，然后对比判断谁更好。

规则：
1. 按得分规则逐条检查 A，记录每条是否满足及理由。
2. 按得分规则逐条检查 B，记录每条是否满足及理由。
3. 分别计算 A 和 B 的总分（满足一条得 1 分，部分满足得 0.5 分，未满足得 0 分）。
4. 总分更高的一方更好。分差 ≤ 0.5 时判 Equal。
5. 忽略排版和客套话，只看实质内容。

输出 JSON：
- "detail_a": "规则1:  正确查到了汇率; 规则2:  缺少时间范围..."
- "score_a": 数字
- "detail_b": "规则1:  正确查到了汇率; 规则2:  有时间范围..."
- "score_b": 数字
- "choice": "Better" / "Equal" / "Worse"（Better = A 更好）
- "reason": "A 总分更高（8 vs 6），主要优势在规则1和规则3"
```

### User Prompt

```
用户问题：
{{query}}

得分规则：
{{ground_truth}}

回复 A：
{{response_a}}

回复 B：
{{response_b}}

请按步骤评估。
```

### Platform 配置

- Score Config：**CATEGORICAL**（Better/Equal/Worse）记录 GSB 结论
- 分数体现在 judge 的 detail 里
- 如果想同时记录分数到 Score Config：跑两次 judge，一次 CATEGORICAL 一次 NUMERIC，用同一个 prompt
- judgeMode：`response_only`
- Langfuse Prompt 类型：**Text**

---

## 怎么选

```
有打分点吗？
├── 没有 → 有两个模型吗？
│   ├── 有 → 模式 2（GSB 对比，无打分点版）
│   └── 没有 → 先写打分点，或者用底线检查
└── 有 → 有两个模型吗？
    ├── 有 → 模式 3（打分+对比） 推荐
    └── 没有 → 模式 1（绝对打分）
```

---

## 底线检查（任何模式前先跑）

不管用哪种正式 judge，建议先过一遍底线：

| 检查项 | Score Config | 类型 | 说明 |
|--------|-------------|------|------|
| identity | `identity` | BOOLEAN | 是否泄露了模型身份 |
| 重复 | `底线-Repeat` | BOOLEAN | 是否有大段重复内容 |
| 拒答 | `底线-不合理拒答` | BOOLEAN | 是否不合理地拒绝回答 |

底线不过的 case 即使正式 judge 得分高也不可信先过底线再看分数。

---

## Internal Evaluation Platform Judge 执行模式

上面三种**打分模式**（NUMERIC / GSB / 融合）是 prompt 设计层面的选择。下面是 Internal Evaluation Platform**执行层面**的配置prompt 写好后，用什么方式跑 judge。

### Judge Pattern（执行引擎）

Platform 支持三种 judge pattern，在创建 judge run 时选择：

| Pattern | 机制 | 适合场景 | 关键参数 |
|---------|------|---------|----------|
| **Agent Judge** (`agent`) | 用 coding agent CLI（Claude Code/Codex/AI_Platform CLI/Gemini CLI）执行，有工具能力，可读文件 | 需要分析附件、代码、复杂轨迹 | `agent`（选哪个 CLI）, `timeout` |
| **LLM Judge** (`llm`) | 单次 LLM chat completion，无工具 | 标准文本打分，快速便宜 | `llm_api_type`, `llm_temperature`, `llm_max_tokens` |
| **Script Judge** (`script`) | 用自定义 Python 脚本执行评分逻辑，不调 LLM | 规则化打分、代码执行验证、精确匹配等确定性评测 | `script_config_name` |

**怎么选：**
- 大多数场景用 **LLM Judge** 就够了标准的 prompt + 打分
- 如果 judge 需要读附件（图片/文件）或执行代码来验证 → **Agent Judge**
- 如果打分逻辑是确定性的（正则匹配、代码执行对比、BLEU/ROUGE 等指标）→ **Script Judge**

### judgeMode（Trace 过滤）

决定 judge 能看到被评测 trace 的哪些部分：

| judgeMode | judge 看到什么 | 用途 |
|-----------|---------------|------|
| `response_only`（默认） | 只有最终 assistant 回复 | 评回复质量，不关心过程 |
| `all_trace` | 完整执行 trace（含 system prompt） | 评工具调用、推理过程 |
| `all_trace_without_sp` | 完整 trace，去掉 system prompt | 评过程但不暴露 system prompt |

**建议：** 评回复质量用 `response_only`；评 Agent 行为（工具调用、搜索策略）用 `all_trace_without_sp`。

### Judge Presets（预设配置）

>  **Judge Preset 会随模型版本更新，禁止硬编码。** 执行前用 `node Platform.mjs presets --type orbit_judge` 查询当前可用 judge preset 列表。
>
> 所有 judge preset 默认 temperature=1.0, maxTokens=64000。

### Auto-Judge

Platform 支持给 dataset 配置 auto-judge：rollout batch 完成后自动触发 judge。

配置方式：Dataset 设置 → Auto Judge → 添加 profile（选 preset + score configs + judgeMode）。

每个 profile 独立运行，可以配多个（比如同时用 opus 和 sonnet judge 做交叉验证）。

Script Judge 也支持 auto-judge：选 pattern 为 Script → 只需选 Script Config，不需要 prompt/model/score configs。

### Judge 输出格式

不管哪种 pattern，最终输出都是：

```json
[
  {"name": "score_config_name", "value": 0.8, "comment": "评分理由", "data_type": "NUMERIC"},
  {"name": "gsb", "value": "Better", "comment": "A 更好因为...", "data_type": "CATEGORICAL"}
]
```

---

## Script Judge 详解

### 什么是 Script Config

一个 Script Config 是打包好的 Python 评分脚本，存在 OSS 上，包含 3 个文件：

| 文件 | 内容 |
|------|------|
| `<name>.py` | 评分脚本主体 |
| `<stem>.pyproject.toml` | Python 项目配置 + 依赖声明 |
| `<stem>.uv.lock` | 依赖锁文件（`uv` 管理） |

### 创建 Script Config

Platform UI → 侧边栏 **Script Configs**（`/script-configs`）→ **Create**，填 4 个字段（全部必填）：
- **Script Name (.py)**：脚本名，必须 `.py` 结尾
- **Script**：Python 评分脚本
- **pyproject.toml**：项目配置 + 依赖
- **uv.lock**：锁文件（本地 `uv lock` 生成）

> 目前无 CLI 命令，也可用 API：`POST /api/script-configs`

### 脚本运行时环境

**环境变量（自动注入）：**

| 环境变量 | 内容 |
|----------|------|
| `ORBIT_JUDGE_INPUT` | 数据集 item 输入（JSON） |
| `ORBIT_JUDGE_EXPECTED_OUTPUT` | 期望输出（JSON） |
| `ORBIT_JUDGE_DATA_METADATA` | item metadata（JSON） |
| `ORBIT_JUDGE_SOURCE_TRACE_ID` | 被评 trace ID |
| `ORBIT_JUDGE_BASELINE_TRACE_ID` | 对比 trace ID（GSB 时） |
| `ORBIT_JUDGE_COMPARISON_MODE` | 是否对比模式（`"true"` if baseline） |
| `ORBIT_JUDGE_SOURCE_BATCH_ID` | Source batch ID |
| `JUDGE_WORKSPACE` | 工作目录（`/workspace`） |

**文件系统（`/workspace/`）：**
- `source/trajectory.jsonl`  Source trace 轨迹
- `baseline/trajectory.jsonl`  Baseline trace 轨迹（GSB 时）
- 其他 trace 产物（workspace 文件等）

**辅助库：** Runner 内置 `orbit_judge` 包，提供 `AbstractScriptJudge` 基类、`build_judge_context()` 获取结构化上下文、以及 `fetch_trace()` 等 Langfuse API 封装。

> ️ **重要: trajectory.jsonl 被 response_only 过滤**
>
> Script judge 的 `JUDGE__MODE` **固定为 `response_only`**（Platform server bug: `buildScriptJudgeBatchConfig` 不传 `judgeMode`），导致 `trajectory.jsonl` 只保留最后一轮 user + assistant，**所有 tool_calls 被删除**。
>
> 如果脚本需要分析 tool_calls（搜索词、工具调用等），**必须直接从 Langfuse API 获取原始 trace**：
>
> ```python
> from orbit_judge._traces import fetch_trace
> trace = fetch_trace(os.getenv("ORBIT_JUDGE_SOURCE_TRACE_ID"))
> observations = getattr(trace, "observations", [])
> # 从 TOOL/GENERATION observations 中提取 tool_calls
> ```
>
> 完整解决方案和参考实现见 [eval-script-judge-guide.md](eval-script-judge-guide.md)。

### 脚本输出要求

写 `/workspace/scores.json`：

```json
[
  {"name": "accuracy", "value": 0.95, "comment": "全部正确"},
  {"name": "format", "value": 0.8, "comment": "少了标题"}
]
```

每个 score 必须有 `name` 和 `value`，可选 `comment`、`data_type`、`metadata`。

### 最简示例

**keyword-check.py**
```python
#!/usr/bin/env python3
import json, os

def main():
    workspace = os.environ.get("JUDGE_WORKSPACE", "/workspace")
    metadata = json.loads(os.environ.get("ORBIT_JUDGE_DATA_METADATA", "{}"))
    
    # 读 trace
    response = ""
    traj_path = os.path.join(workspace, "trajectory.jsonl")
    if os.path.exists(traj_path):
        with open(traj_path) as f:
            for line in f:
                msg = json.loads(line)
                if msg.get("role") == "assistant":
                    response = msg.get("content", "")
    
    # 评分：关键词覆盖率
    keywords = metadata.get("keywords", "").split(",")
    hits = sum(1 for kw in keywords if kw.strip() in response)
    score = hits / max(len(keywords), 1)
    
    scores = [{"name": "keyword_coverage", "value": score,
               "comment": f"命中 {hits}/{len(keywords)} 个关键词"}]
    with open(os.path.join(workspace, "scores.json"), "w") as f:
        json.dump(scores, f, ensure_ascii=False)

if __name__ == "__main__":
    main()
```

**pyproject.toml**
```toml
[project]
name = "keyword-check"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**uv.lock**
```
version = 1
revision = 3
requires-python = ">=3.11"
```

### 执行流程

```
Platform → 创建 judge batch（JUDGE__PREPARE_MODE=script）
  → Runner 容器启动
    → prepare(): 拉 dataset item → 设环境变量 → 还原 trace → 从 OSS 下载脚本
    → 写脚本到 /workspace/judge_scripts/
    → uv sync --locked → 创建隔离 venv
    → 执行: .venv/bin/python <name>.py（cwd=/workspace）
    → 读 /workspace/scores.json → 上报 Langfuse
```

### 跑 Script Judge

**UI**：Judges → New Judge → Source Batch → Judge Pattern 选 **Script Judge** → 选 Script Config → Run Judge

**API**：
```bash
curl -X POST "https://platform.internal.ai.com/api/judges/runs" \
  -H "X-AuthGateway-Access-Token: $AuthGateway_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"judgePattern": "script", "sourceBatchId": 12345, "scriptConfigName": "keyword-check.py"}'
```

> Script Judge 不需要选 prompt、model、score config全靠脚本自己定义输出。

---

## 参考实现

- **Script Judge 开发指南**：[eval-script-judge-guide.md](eval-script-judge-guide.md)  完整开发流程、踩坑经验、调试技巧
- **搜索词时效性 GSB Judge**：`scripts/judge/web_search_timeliness_judge.py`  Langfuse observation 解析 + GSB 对比完整示例
- Chatty 链路的可执行 judge：`scripts/judge/judge.py` + `scripts/judge/judge_prompt/prompt.py`
- Platform 链路操作指南：[rollout-Platform-guide.md](rollout-Platform-guide.md) → Judge 章节
- Platform Judge 源码：`harness/orbiverse` → `apps/Platform-judge/src/orbit_judge/`
- Platform Judge 预设：`harness/orbiverse` → `apps/Platform/lib/presets/judge.ts`
- Script Config 管理：`harness/orbiverse` → `apps/Platform/lib/workspace/script-configs.ts`
