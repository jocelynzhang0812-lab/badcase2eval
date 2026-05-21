---
name: eval-skill
description: |
  产品体验 Benchmark 全流程工具。从发现 badcase 到构造 benchmark、跑评测、分析结果的完整闭环。
  支持两条评测链路：Chatty 直连（搜索评测、可对比外部模型）和 Internal Evaluation Platform（内部模型持续观测）。
  Triggers on: eval, benchmark, bmk, 评测, badcase, 价值观, 构造数据集, 跑评测, judge, 搜索评测,
  体验评测, 模型对比, badcase 收录, 打标, 数据质量验证, 持续观测, 评测报告, 敏感词, 替换, 脱敏, PII, 个人信息, 身份证号, 隐私,
  送评, checkpoint, batch, 分数统计, 写分析, 送评结果, 分析文档, 设计文档, bench 规范, 归档, 数据归档.
---

# Eval Skill  产品体验 Benchmark

本 skill 是评测全流程的**调度中心**。根据用户意图，路由到对应的工具、文档或[Internal Docs Platform]知识库去执行。

> **Platform 问题查源码**：遇到本 skill 文档无法回答的 Platform 问题时，去 `https://internal.company.com/harness/orbiverse` monorepo（Platform 源码在 `apps/Platform` 目录）查看源码和文档来回答。

---

##  执行纪律（每次操作前必读）

> **以下规则优先级高于一切。违反任何一条都可能导致评测配置错误、资源浪费。**

1.  **必须按 [§④ 跑评测](#④-跑评测) 的完整流程执行**：查配置 → 展示确认 → 拼命令(dry-run) → 跑预检 → 正式执行 → 算分数。**绝对不能跳过任何步骤。**
2.  **跑 Rollout 前必须展示确认清单**：按 [Platform-interaction-principles.md](references/Platform-interaction-principles.md#运行前确认清单模板) 中的模板向用户确认所有参数，用户确认后才能执行。确认判定标准详见该文档（「好的」「可以」等视为确认）。
3.  **运行前预检（Pre-flight Check）**：dry-run 通过后、正式执行前，必须执行 [preflight-check.md](benchmarks/preflight-check.md) 中的**四步预检**：
   - **AKSK 检查**：`python scripts/rollout-setup_aksk.py --check`，确认密钥配置完整
   - **模型健康检查**：`model-health --model <rollout模型>` + `model-health --model <judge模型>`，确认节点可用
   - **成本估算**：根据评测方向和 tasks 数量估算 judge 花费
   - **余额检查**：`balance` 查Internal_AI_Service余额，余额不足时  停止并提醒用户
4.  **不要替用户选配置**：用户未指定的参数自动用默认值填充，在确认清单中一次性展示（含 prompt），不要逐个参数单独询问。
5.  **跑评测时，关键配置（dataset / prompt / preset / model 等）必须从 Platform CLI 实时查询确认，不得仅凭历史记忆复用**。上下文可用于理解用户意图，但执行参数必须以 CLI 最新返回为准。正式执行前向用户展示完整确认清单。
5. **上传完成后自动校验**：用 `scripts/data-verify_upload.py` 检查一致性。
6. **各步骤的具体暂停点**：在对应的 reference 文档里定义，按文档指示操作。

---

##  指令速查（用户说 → 去哪里）

> 一页速查，覆盖所有常见指令。详细说明见下方各章节。

### 跑评测 & 管理

| 用户说 | → 工具 / 文档 |
|-------|-------------|
| "跑一下" / "run" / "roll" | → 下方 [§④ 跑评测](#④-跑评测) |
| "judge" / "打分" | → 下方 [§⑤ 打分](#⑤-打分-judge) |
| "arena" / "跑 arena" | → 下方 [§④ 跑评测](#④-跑评测)（Arena 配置见 [evaluation-types.md](benchmarks/evaluation-types.md) §3-4） |
| "看进度" / "describe" | Platform CLI `describe --batch <id>` |
| "暂停" / "继续" / "重试" | Platform CLI `pause` / `resume` / `retry` |
| "导出" / "分数" | Platform CLI `export` / `scores`，算分规则见 [§⑥ 分析结果](#⑥-分析结果) |
| "查 preset / dataset / prompt" | Platform CLI `presets` / `datasets` / `prompts` |
| "查 tag / 模型别名 / score config" | [evaluation-types.md](benchmarks/evaluation-types.md) |

### 数据准备

| 用户说 | → 工具 / 文档 |
|-------|-------------|
| "从[Internal Docs Platform]表格拉数据" | `scripts/data-bitable_to_orbit.py` (依赖 kitty-feishu) |
| "CSV 转 Platform" | `scripts/data-csv_to_orbit.py` → [data-csv-to-Platform.md](references/data-csv-to-Platform.md) |
| "上传数据集" | Platform CLI `upload` |
| "上传附件" | Platform CLI `upload-attachments` |
| "校验上传" | `scripts/data-verify_upload.py` |
| "LLM 打标 / bloom 生成" | `scripts/data-ask_llm.py` / `data-bloom_generate.py` (依赖 ai_service) |
| "AI_Code_Platform 日志转 Platform" | `scripts/data-kimicode_convert_to_orbit.py` |

### 发现问题 & Badcase

| 用户说 | → 工具 / 文档 |
|-------|-------------|
| "拉 trace" / "看 chat_id" | `scripts/data-get_message.py` |
| "收录到 Platform" / "带附件上传" / "批量收录" | `scripts/data-orbit_lens_collect.py`（Platform Lens API，自动处理附件/图片，30 并发） |
| "收录 badcase" | [data-badcase-flow.md](references/data-badcase-flow.md) |
| "从数仓批量挖 badcase" / "Insight" | [data-insight-flow.md](references/data-insight-flow.md) (依赖 data-assistant) |
| "查埋点" / "用户行为" | `scripts/data-query_buried_point.py` → [data-volc-event-logs.md](references/data-volc-event-logs.md) |
| "查反馈" / "点踩" | `scripts/data-query_feedback.py` → [data-feedback-db.md](references/data-feedback-db.md) |
| "查数仓" / "SQL 查询" | data-assistant skill |

### 分析 & 报告

| 用户说 | → 工具 / 文档 |
|-------|-------------|
| "分析结果" / "哪些 case 失败" | [eval-review-Platform-results.md](references/eval-review-Platform-results.md) |
| "分析轨迹" / "tool_call" | `scripts/eval-analyze_trajectory.py` → [eval-trajectory.md](references/eval-trajectory.md) |
| "写评测报告" | [bench-report-writing.md](references/bench-report-writing.md) + `scripts/bench-report/` |
| "导出 CSV" | `scripts/eval-export_batch_csv.py` |
| "事实核查" | `scripts/eval-fact_check.py` |

### 数据集质量 & 安全

| 用户说 | → 工具 / 文档 |
|-------|-------------|
| "扫描敏感词" | `scripts/bmk-scan_keywords.py` → [bmk-dataset-audit.md](references/bmk-dataset-audit.md) |
| "替换敏感词" | `scripts/bmk-replace_keywords.py` |
| "脱敏" / "PII" / "身份证号" | `scripts/data-sanitize_pii.py` |
| "验证数据质量" | [bmk-validity.md](references/bmk-validity.md) |

### 配置 & 排查

| 用户说 | → 工具 / 文档 |
|-------|-------------|
| "配置 AKSK" | `scripts/rollout-setup_aksk.py` |
| "task 失败" / "诊断" | Platform CLI `diagnose` / `inspect` → [debug.md](Platform/references/debug.md) |
| "PPT/网页/文档问题" | [Internal_Tool-trajectory-troubleshooting.md](references/Internal_Tool-trajectory-troubleshooting.md) |
| "Internal_Tool 工具使用示例" / "轨迹调试" | [eval-tool-usage-examples.md](references/eval-tool-usage-examples.md) |
| "x35 工具规范" / "工具调用对错" | [eval-x35-tool-guidelines.md](references/eval-x35-tool-guidelines.md) |
| "从零建 benchmark" | [getting-started.md](references/getting-started.md) |
| "怎么写 judge prompt" | [eval-judge-modes.md](references/eval-judge-modes.md) |
| "Script Judge 开发" | [eval-script-judge-guide.md](references/eval-script-judge-guide.md) |

---


## 全局流程

不是每次都从 ⓪ 开始匹配用户意图，定位到对应步骤直接执行。从零创建新 benchmark 从 ⓪ 开始。

---

## 可用工具

| 工具 | 位置 | 说明 |
|------|------|------|
| **Platform CLI** | 本仓库 `Platform/Platform.mjs` | Internal Evaluation Platform操作（run/judge/upload/export/trace 等） |
| **Platform Lens** | `scripts/data-orbit_lens_collect.py` | 通过 Platform Lens API 批量收录 chat/segment（自动处理附件/图片，30 并发） |
| **本 skill 脚本** | 本仓库 `scripts/` | 数据处理、格式转换、PII 脱敏、分析等 |
| **kitty-feishu** skill | 外部 skill | 读写[Internal Docs Platform]文档、多维表格 |
| **ai_service** skill | 外部 skill | 调用 LLM API（Internal_AI_Service网关） |
| **red-model-deploy** skill | 外部 skill | 部署待评测模型到 GPU 集群 |

---

## ⓪ 从零创建 Benchmark

| 用户说 | → 去哪里 |
|-------|----------|
| "从头做个评测" / "新建 benchmark" / "什么都没有" | → 读 [getting-started.md](references/getting-started.md) 按 7 步走（定义目标 → 设计打分 → 写 Judge Prompt → 选参数 → 构造数据 → 试跑 → 正式跑+持续迭代） |
| "怎么写 judge prompt" / "从零设计打分" | → 读 [eval-judge-modes.md](references/eval-judge-modes.md) + [getting-started.md](references/getting-started.md) Step 2-3 |
| "用什么 preset" / "参数怎么选" | → 读 [getting-started.md](references/getting-started.md) Step 4 + [rollout-Platform-guide.md](references/rollout-Platform-guide.md) |
| "收录到大 bmk" / "上线 SOP" / "想上一个改动" | → 走下方「产品改动上线 SOP」 |
| "查大 bmk 有哪些数据集" / "看收录表" | → 读 [产品大bmk](https://internal-docs.company.com/base/YD1jbZLxpavDIZsoW7QcaDKvnMd?table=tblcjZKhFQewuljv&view=vewpE95Wnp)，获取所有已收录数据集的 Platform Dataset ID、Judge 配置 |

### 产品改动上线 SOP

想上一个改动（prompt 改版、新功能、模型切换等），走这个流程：

| 步骤 | 做什么 | 谁做 |
|------|--------|------|
| ① 出小 bmk | 自己构造数据集，在 Platform 跑通 rollout + judge。参考 [小 bmk 构造指南](https://internal-docs.company.com/wiki/TcKzwfzBCiLuTFkRxvccmesRnBe) | 提需人 |
| ② 收录到大 bmk | 给 [Colleague Name 1]，登记到 [产品大bmk](https://internal-docs.company.com/base/YD1jbZLxpavDIZsoW7QcaDKvnMd?table=tblcjZKhFQewuljv&view=vewpE95Wnp)，填 Platform Dataset ID、场景、Judge 配置 | 提需人 + [Colleague Name 1] |
| ③ 批量跑 BL vs EXP | 用大 bmk 里所有相关数据集跑 baseline vs experiment，确认无回退 | 提需人 |
| ④ 真实环境验证 | @田新天 给真实环境 Chatty 入口，端到端测一遍 | 提需人 + @田新天 |
| ⑤ 上线 | 没问题就上 | 提需人 |

---

## ① 发现问题

| 用户说 | → 去哪里 |
|-------|----------|
| "帮我看看这个 chat_id" / "拉 trace" | → 本 skill `scripts/data-get_message.py`（支持 chat_id / share_id / share link） |
| "上传到 Platform" / "收录这个 case" / "带附件上传" | → 本 skill `scripts/data-orbit_lens_collect.py`（从 AI_Platform chat_id/segment/share link 收录，自动处理附件和图片） |
| "批量收录 chat_id" / "批量上传" | → 本 skill `scripts/data-orbit_lens_collect.py --from-file`（30 并发） |
| "这个 case 有问题" / "收录 badcase" | → 读 [data-badcase-flow.md](references/data-badcase-flow.md) Step 1-3 |
| "验证能不能复现" / "跑 10 次" | → 读 [data-badcase-flow.md](references/data-badcase-flow.md) Step 4-7 |
| "把 badcase 加到 bmk" | → 读 [data-badcase-flow.md](references/data-badcase-flow.md) Step 8 |
| "看 Agent Step 级别 trace" | → 本 skill `scripts/data-fetch_chat_requests.py` ️ 需 kimi_python |
| "从 trace 构造数据集" / "A/B 换 SP" | → 本 skill `scripts/data-trace_to_orbit.py`（从已有 trace JSON 构造 dataset item，支持精确 turn/step 控制 + 替换 SP 做 A/B） |
| "从线上数仓 SQL 批量挖 badcase" / "Fuck Bench" / "定期扫线上对话" / "用 Insight 找 chat_id" | → 读 [data-insight-flow.md](references/data-insight-flow.md)  Insight SQL → bitable → get_message → 标注 → Platform 的完整批量链路（依赖 `data-assistant` skill 查数仓） |

> **turn_step 说明**：1-indexed。精确到 step（如 `22-1`）→ API 直打，测回复质量；精确到 turn → Platform 重放，测工具行为。

---

## ② 准备数据

| 用户说 | → 去哪里 | 依赖 |
|-------|----------|------|
| "从[Internal Docs Platform]表格拉数据" | → 本 skill `scripts/data-bitable_to_orbit.py` | **kitty-feishu** |
| "[Internal Docs Platform]表格直接传 Platform" | → 本 skill `scripts/data-bitable_to_orbit.py --upload` | **kitty-feishu** + Platform CLI |
| "CSV 转 Platform 格式" | → 本 skill `scripts/data-csv_to_orbit.py` | 无 |
| "badcase 表转数据集" | → 本 skill `scripts/data-badcase_to_orbit.py`（需先用 ① 拉 trace） | 无 |
| "生成评测场景" / "bloom" | → 本 skill `scripts/data-bloom_generate.py` | **ai_service** |
| "多轮对话探测" | → 本 skill `scripts/data-bloom_rollout.py` | **ai_service** |
| "LLM 打标分类" | → 本 skill `scripts/data-ask_llm.py` | **ai_service** |
| "AI_Code_Platform 日志转 Platform" / "Internal_AI_Service日志上传" | → 本 skill `scripts/data-kimicode_convert_to_orbit.py` | 无 |

字段类型（Input vs Metadata）规则见 [data-csv-to-Platform.md](references/data-csv-to-Platform.md)。

---

## ③ 上传 Platform

| 用户说 | → 去哪里 |
|-------|----------|
| "上传数据" | → Platform CLI `upload` |
| "上传附件" | → Platform CLI `upload-attachments`，详见 [data-csv-to-Platform.md](references/data-csv-to-Platform.md) 附件章节 |
| "校验上传" | → 本 skill `scripts/data-verify_upload.py`（支持 `--file` / `--bitable` / `--trace` / `--source-dataset`） |

---

## ④ 跑评测

### 文档职责与 SSOT

跑评测涉及 **4 类文档**，各管一件事：

| 文档 | 职责 | SSOT 范围（只在这里维护，其他文件只引用） | 什么时候读 |
|------|------|------|----------|
| [benchmarks/](benchmarks/README.md)（导航） | 评测入口 |  | **不确定该查哪个文件时**从这里开始 |
| [evaluation-types.md](benchmarks/evaluation-types.md) | **跑什么、怎么配** | tag 别名、模型别名、通用默认参数、8 种评测类型配置与算分规则 | 每次跑评测前查配置 |
| [rollout-Platform-guide.md](references/rollout-Platform-guide.md) | **配置参考** | Preset 选择逻辑、Prompt 切换、Tools/AKSK/Judge 配置 | 首次跑 / 不确定参数时 |
| [Platform/SKILL.md](Platform/SKILL.md) | **CLI 语法** | 命令格式、flag 语法、Request Translation SOP | 拼命令时查 |
| [score-calculation.md](benchmarks/score-calculation.md) | **算分 + 填表** | 算分公式、[Internal Docs Platform]表格结构、填表流程 | 算分和填表时查 |

>  **SSOT 约定**：上表 SSOT 范围即该文件的唯一权威数据。其他文件引用时应链接过来而不是复制。若发现矛盾，以 SSOT 文件为准。

**标准执行流程：**

```
① 查配置   evaluation-types.md    tag/模型/concurrent/默认参数/类型特殊规则
    ↓
② 展示确认  Platform-interaction-principles.md  确认清单模板
    ↓
③ Dry-run   Platform/SKILL.md          --dry-run 验证配置无误
    ↓
④ 跑预检   preflight-check.md      AKSK + 模型健康 + 成本 + 余额（四步）
    ↓
⑤ 正式执行（去掉 --dry-run）
    ↓
⑤b 等待完成  创建 15 分钟后开始轮询，间隔 10 分钟
    ↓
⑥ 算分数   score-calculation.md    拉分数 + 加权 + 填[Internal Docs Platform]表
```

| 用户说 | → 去哪里 |
|-------|----------|
| "跑一下" / "run 这个数据集" | → 按上述流程执行（①→②→③→④→⑤→⑥） |
| "关掉 thinking" / "用空 prompt" / "用自部署模型" | → [rollout-Platform-guide.md](references/rollout-Platform-guide.md) 对应章节 + [Platform/SKILL.md](Platform/SKILL.md) §Request Translation |
| "交互式全流程"（上传→run→judge） | → 本 skill `scripts/rollout-run_eval.py` |
| "看进度" / "暂停" / "继续" / "重试" | → Platform CLI `describe` / `pause` / `resume` / `retry` |
| "终止任务" / "杀掉这个 task" | → Platform CLI `terminate --task <taskId>` |
| "下载结果" / "导出 zip" | → Platform CLI `download --batch <batchId>` |
| "task 失败了" / "看 trace" / "看日志" | → Platform CLI `inspect` / `trace` / `logs` |
| "这个 dataset 跑过哪些 runs" | → Platform CLI `dataset-runs --dataset <name>` |
| "看 score configs" / "创建打分配置" | → Platform CLI `score-configs` |
| "看 script configs" / "管理脚本 judge" | → Platform CLI `script-configs` |
| "监控 batch" / "batch 跑完了吗" | → `scripts/batch_monitor.py --watch <id>` 或 `--check <id>` |
| "存档" / "记录 batch id" | → 下方 [§⑤c 运行记录存档](#⑤c-运行记录存档) |
| "查余额" / "还够不够跑" / "估算成本" | → [preflight-check.md](benchmarks/preflight-check.md)，Platform CLI `balance` + `model-health` |
| "找某个 tag 的数据集" / "列出所有 tag" | → `scripts/dataset_tag_indexer.py --find <tag>` 或 `--list-tags` |

### Chatty 链路（补充）

| 用户说 | → 去哪里 |
|-------|----------|
| "用 Chatty 跑" | → 本 skill `scripts/rollout-batch_chatty.py` ️ 需 opentelemetry |
| "重放 trace" | → 本 skill `scripts/rollout-replay_chatty.py` |
| "对比两组结果" | → 本 skill `scripts/bmk/compare.py` |

---

## ⑤ 打分 (Judge)

> **文档层次**：本节只做路由。打分模式详解 → [eval-judge-modes.md](references/eval-judge-modes.md)；CLI 参数 → [Platform SKILL.md](Platform/SKILL.md) §Parameter Checklist；Script Judge → [eval-script-judge-guide.md](references/eval-script-judge-guide.md)。

先读 [eval-judge-modes.md](references/eval-judge-modes.md) 确定三件事：
1. **打分模式**：绝对打分(NUMERIC) / GSB 对比(CATEGORICAL) / 打分+对比（融合）
2. **执行模式（judgePattern）**：`agent`（有工具）/ `llm`（单次调用无工具）/ `script`（自定义脚本）
3. **上下文范围（judgeMode）**：
   - `response_only`（默认） 只看最终回复
   - `all_trace`  看完整 trace（含 system prompt）
   - `all_trace_without_sp`  看完整 trace 但去掉 SP

> ️ **2026-04-09 起 `judgePattern` 必填**。CLI 用 `--judge-pattern llm|agent|script`。`judgeMode` 通过 `--payload-json` 传入。

| 用户说 | → 去哪里 |
|-------|----------|
| "打分" / "judge 一下" | → 先 Platform CLI `describe` 查 auto-judge，有则 `trigger-judge`，无则问用户三件事（打分模式、judgePattern、judgeMode）后 Platform CLI `judge` |
| "用 xxx judge" | → `presets --type orbit_judge` 查询匹配的 judge preset，然后 Platform CLI `judge --preset <matched_preset>` |
| "用 agent judge" / "需要读附件" | → `presets --type orbit_judge` 查询，Platform CLI `judge --preset <preset>`（Agent pattern，默认） |
| "用 llm judge" / "快速打分" | → Platform CLI `judge` 选 LLM pattern（无工具，更快更便宜） |
| "用脚本打分" / "规则化评测" | → Platform CLI `judge` 选 Script pattern + script config，读 [eval-script-judge-guide.md](references/eval-script-judge-guide.md) |
| "重新打分" / "补 judge" | → Platform CLI `trigger-judge` / `backfill-judge` |
| "看 trace 打分" / "评工具调用" | → judgeMode 选 `all_trace_without_sp`，详见 [eval-judge-modes.md](references/eval-judge-modes.md) Internal Evaluation Platform章节 |
| "Chatty LLM Judge" | → 本 skill `scripts/judge/judge.py`，prompt 模板在 `scripts/judge/judge_prompt/` |
| "事实核查" | → 本 skill `scripts/eval-fact_check.py` |

---

## ⑤c 运行记录存档

> **每次完成 Platform batch run 后，主动询问用户："是否需要将本次运行记录存档？"**

**存档表格**：[Internal Docs Platform]电子表格 `BYnpsmGfqhZvnqtu2o1ceZ5xn3h`（运行记录 batch id 存档）

**现有 Sheet：**
| Sheet ID | 名称 | 内容 |
|----------|------|------|
| `0guDTs` | Text Benchmark Batch IDs | 18 datasets × 10 models |
| `2pBAhG` | Vision Benchmark Batch IDs | 15 datasets × 8 models |
| `3vi5EY` | Arena Benchmark Batch IDs | 2 datasets × 25 models |
| `140yT6` | Chat_withtools Batch IDs | 10 datasets × 19 models |

**存档规则：**
1. 用户要求"存档"时，将 batch ID、模型名、数据集等信息写入上述[Internal Docs Platform]表格的对应 sheet
2. 如果是新的 benchmark 方向，创建新 sheet
3. **表格格式**：行 = 数据集，列 = 模型，单元格 = batch ID（纯数字）
4. 使用 `kitty-feishu` skill 写入：`KittyFeishuClient(session_id).write_sheet_range(token, 'sheetId!A1:Z50', [[row_data]])`

---

## ⑥ 分析结果

| 用户说 | → 去哪里 |
|-------|----------|
| "分数怎么样" | → Platform CLI `scores` → 用人话展示。算分规则详见 [score-calculation.md](benchmarks/score-calculation.md) |
| "跑一下 text/vision/arena/withtools/专项/底线/安全" | → 各8种评测类型的运行配置与算分规则详见 [evaluation-types.md](benchmarks/evaluation-types.md) |
| "导出数据" | → Platform CLI `export` |
| "导出 CSV" / "转[Internal Docs Platform]表格" | → 先 Platform CLI `export` 导 JSONL，再 `scripts/eval-export_batch_csv.py` 转 7 列 CSV（query/keypoint/baseline/eval/judge_result_answer/judge_result_toolcall/judge） |
| "哪些 case 失败了" / "对比 batch" | → 读 [eval-review-Platform-results.md](references/eval-review-Platform-results.md) |
| "分析搜索词 / tool_call" | → 本 skill `scripts/eval-judge_trajectory.py`，读 [eval-trajectory.md](references/eval-trajectory.md) |
| "分析 Agent 轨迹" | → 本 skill `scripts/eval-analyze_trajectory.py` |
| "拉完整轨迹" | → 本 skill `scripts/data-get_full_trajectory.py` |
| "Review Judge 准不准" | → 读 [eval-review-Platform-results.md](references/eval-review-Platform-results.md) Step 4 |
| "写评测报告" | → 读 [eval-review-Platform-results.md](references/eval-review-Platform-results.md) 报告模板 |
| "写[Internal Docs Platform]评测报告" / "图文混排测评分析" | → 读 [bench-report-writing.md](references/bench-report-writing.md)（5 段结构 + 4 类图 + [Internal Docs Platform]图文混排, scripts 在 `scripts/bench-report/`） |
| "送评分析怎么写" / "查写作规范" / "问题怎么分级" | → 查 [[Internal Docs Platform]评测知识库](https://internal-docs.company.com/wiki/space/7629344887481043916)（送评分析 6 章结构、分级标签、检查清单、历史案例，动态更新） |
| "哪些评分项有缺失" / "覆盖率统计" | → 读 [Platform-score-coverage.md](references/Platform-score-coverage.md) |

### 送评分析写作规范（[Internal Docs Platform]知识库）

写送评分析报告时涉及[Internal Docs Platform] Wiki 操作，遵循以下规则：

1. **先读入口页**：任务涉及[Internal Docs Platform]知识库时，第一步读入口页 `G0bcw6CgjioH1Sk8Wo9cjIWxnMb` 获取精确 token，不要凭印象猜。
2. **新建/删除节点后更新入口页**：操作完成后把最新 token 同步回入口页索引表，保持"真相来源"最新。
3. **归档路径**：`送评分析文档 / {ModelName}结果分析 / {checkpoint} / {bench_type}`
   - 送评分析文档根节点：`Q1ZywVG4hiHhYmkKvWkcreLRnIb`
   - model_checkpoint结果分析：`AvqGw8Oooiz30lkmjAzcdcWmnvc`

---

## 辅助功能

### 数据集管理

| 用户说 | → 去哪里 |
|-------|----------|
| "验证数据集质量" | → [bmk-validity.md](references/bmk-validity.md) |
| "扫描 / 替换敏感词" | → [bmk-dataset-audit.md](references/bmk-dataset-audit.md)，用 `scripts/bmk-scan_keywords.py` 或 `bmk-replace_keywords.py` |
| "脱敏" / "PII" / "个人信息" / "身份证号" / "去掉密码" | → 读 [bmk-dataset-audit.md](references/bmk-dataset-audit.md) Step 6，用 `scripts/data-sanitize_pii.py`（先 scan 再 redact） |

### 埋点查询

| 用户说 | → 去哪里 |
|-------|----------|
| "查埋点" / "用户做了什么" | → 读 [data-volc-event-logs.md](references/data-volc-event-logs.md)，用 `scripts/data-query_buried_point.py` |

### 反馈查询

| 用户说 | → 去哪里 |
|-------|----------|
| "查反馈" / "用户点踩" | → 读 [data-feedback-db.md](references/data-feedback-db.md)，通过 **data-assistant** skill 查数仓 |

### 送评分析规范

| 用户说 | → 去哪里 |
|-------|----------|
| "送评分析怎么写" / "查写作规范" / "检查清单" | → [[Internal Docs Platform]评测知识库](https://internal-docs.company.com/wiki/space/7629344887481043916)（6 章结构、分级标签、自查清单，**动态更新以知识库为准**） |
| "问题怎么分级" / "标签定义" | → 知识库中的问题分级标准（严重/中等/轻微/还行） |
| "参考历史案例" / "model_checkpoint 送评" | → 知识库中的 Checkpoint 送评分析案例 |

### 配置 AKSK

| 用户说 | → 去哪里 |
|-------|----------|
| "配置 AKSK" | → 本 skill `scripts/rollout-setup_aksk.py --check` |

---

## 首次使用

环境配置、Key 获取方式详见 [README.md](README.md) §快速开始。核心三步：

```bash
pip install -r requirements.txt
cp .env.example .env  # 填入 AuthGateway_ACCESS_TOKEN, OPENAI_API_KEY 等
source .env && python scripts/rollout-setup_aksk.py
```

---

## References

| 文件 | 内容 |
|------|------|
| [getting-started.md](references/getting-started.md) | **从零创建 Benchmark** 7 步引导（定义目标→设计打分→写 Prompt→选参数→构造数据→试跑→正式跑+迭代） |
| [data-badcase-flow.md](references/data-badcase-flow.md) | Badcase 链路：发现 → 收录 → 复现 → 进 BMK（**单条**手动流程）|
| [data-insight-flow.md](references/data-insight-flow.md) | **Insight SQL → bitable → get_message → 标注 → Platform** 的**批量**定期挖掘流程（从数仓主动挖 badcase），Fuck Bench 即此流程的首个实战案例 |
| [data-badcase-to-bmk.md](references/data-badcase-to-bmk.md) | 从 badcase 表构造 benchmark 数据集 |
| [data-csv-to-Platform.md](references/data-csv-to-Platform.md) | 数据格式转换 + 附件上传 |
| [bmk-validity.md](references/bmk-validity.md) | 数据集质量验证 |
| [eval-judge-modes.md](references/eval-judge-modes.md) | Judge 三种打分模式 + prompt 模板 |
| [eval-script-judge-guide.md](references/eval-script-judge-guide.md) | Script Judge 开发指南 |
| [eval-trajectory.md](references/eval-trajectory.md) | 评测轨迹分析 |
| [eval-tool-usage-examples.md](references/eval-tool-usage-examples.md) | Internal_Tool Trajectory Debugger 使用示例（5 个分析场景） |
| [eval-x35-tool-guidelines.md](references/eval-x35-tool-guidelines.md) | x35 工具使用规范（data source / search / image / fetch / ipython） |
| [eval-review-Platform-results.md](references/eval-review-Platform-results.md) | 评测结果分析 + 报告模板 |
| [bench-report-writing.md](references/bench-report-writing.md) | **[Internal Docs Platform]评测分析报告写作**  5 段结构 + 4 类图 + 段落-图混排 + 写作语言纪律 |
| [rollout-Platform-guide.md](references/rollout-Platform-guide.md) | Platform 配置参考（Preset/Prompt/Model/Tools/Judge） |
| [score-calculation.md](benchmarks/score-calculation.md) | **算分 pipeline**  traceIds 查询、3 种评分类型公式、多 Batch 加权平均、[Internal Docs Platform]填表、8 条必须规则 |
| [evaluation-types.md](benchmarks/evaluation-types.md) | **评测配置与类型规格**  tag/模型别名、默认参数、Score Config、8 种评测类型运行配置与算分规则 |
| [Platform-interaction-principles.md](references/Platform-interaction-principles.md) | **交互原则**  确认判定标准、DO/DON'T、红线行为、确认清单模板 |
| [preflight-check.md](benchmarks/preflight-check.md) | **运行前预检**  模型健康检查、成本估算、余额检查（[wiki 花销表](https://internal-docs.company.com/wiki/CChqwIQWAiiJBjkswagcIEYhnfb?sheet=4e5997)） |
| [Platform-score-coverage.md](references/Platform-score-coverage.md) | 评分项覆盖率统计（succeed/fail 计数） |
| [data-volc-event-logs.md](references/data-volc-event-logs.md) | 火山埋点查询 |
| [data-feedback-db.md](references/data-feedback-db.md) | 用户反馈查询 |
| [bmk-dataset-audit.md](references/bmk-dataset-audit.md) | 敏感词扫描与替换 |
| [[Internal Docs Platform]评测知识库](https://internal-docs.company.com/wiki/space/7629344887481043916) | 送评分析写作规范、问题分级标签、检查清单、Checkpoint 历史案例（**动态更新**） |
