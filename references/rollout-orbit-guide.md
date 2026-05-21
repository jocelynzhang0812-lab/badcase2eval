# Platform 配置参考  Preset / Prompt / Model / Tools

选 Preset、配 Prompt、查 Model、设 Tools/AKSK 的权威参考。概念解释 + 手把手教怎么配。

>  **Preset 配置会随模型版本迭代变化，禁止硬编码。** 执行前必须用 `node Platform.mjs presets` 动态查询当前可用列表。

---

## Preset（选预设，自动配好一切）

Preset = 预设配置包。选一个就自动配好 Prompt、Model、Tools。**你不用自己配参数，选一个就行。**

### AI_Platform 系列（稳定）

| Preset | 说明 | 什么时候用 |
|--------|------|-----------|
| `kimi_chat` | 评测 AI_Platform chat 主流程（搜索、对话、引用） | 日常评测 AI_Platform 线上 chat 体验 |
| `kimi_agent` | 评测 AI_Platform agent 流程（代码执行、文件操作） | 评测 agent 能力 |
| `kimi_cli` | 评测 AI_Platform CLI 流程 | CLI 评测 |

### 外部模型 & Judge Preset

>  **外部模型和 Judge 的 preset 会随模型版本更新（如 opus_4_5 → opus_4_6），不在此列举。**
>
> - **查询 Rollout Preset**：`node Platform.mjs presets`
> - **查询 Judge Preset**：`node Platform.mjs presets --type orbit_judge`
> - 用户说"opus / sonnet / gpt / gemini"→ 从 `presets` 返回列表中匹配含该关键词的 preset

### 特殊 Preset

| Preset | 说明 | 什么时候用 |
|--------|------|-----------|
| `self_deployed` | 自部署模型，需自己指定 `--model` 和 `--api-base-url` | 测新训练的 checkpoint |
| `custom` | 完全自定义，所有参数都要自己传 | 特殊场景 |

### 怎么选

| 你想做什么 | 怎么做 |
|-----------|--------|
| 评测 AI_Platform 线上 chat 体验 | `--preset kimi_chat` |
| 评测 AI_Platform agent 能力 | `--preset kimi_agent` |
| 评测 AI_Platform CLI | `--preset kimi_cli` |
| 对比 AI_Platform 和外部模型 | `kimi_chat` + 外部 preset（`presets` 查询）各跑一次 |
| 测新训练的模型 | `--preset kimi_chat --model <模型名> --api-base-url <地址> --dry-run` |
| 禁用 thinking 看效果 | 任意 preset + `--thinking 0` |

### 三种评测场景

| 场景 | 目的 | 怎么跑 |
|------|------|--------|
| 验证 tool spec | 用外部模型确认 tool spec 没问题 | 用 `presets` 查询外部模型 preset |
| 验证 AI_Platform best 表现 | AI_Platform + enforcer 开启（线上状态） | `--preset kimi_chat`（默认开启 enforcer） |
| 模拟线上 worst 表现 | AI_Platform + enforcer 关闭（见 [Model → LLM Extra Body](#llm-extra-body)） | `--preset kimi_chat` + `extraBody: {"enforcer_mode": "off"}` |

---

## Prompt（Rollout 的 System Prompt）

Prompt = 模型执行任务时的 System Prompt。选了 Preset 后会自动绑定一个默认 Prompt，也可以手动切换。

> ️ **不要和 Judge Prompt 混淆！**
> - **Rollout Prompt**（本章节）= 告诉被测模型你是谁、怎么做事，在 Langfuse 上创建，类型选 **Chat**
> - **Judge Prompt**（见下方 Judge 章节）= 告诉打分模型怎么评分，在 Langfuse 上创建，类型选 **Text**

### Preset 绑定的 Prompt

>  **Prompt 名称会随版本更新，禁止硬编码。** 执行前用 `node Platform.mjs presets` 查看各 preset 当前绑定的默认 prompt。
>
> 特殊规则：`empty` prompt（空 system prompt）始终可用，**必须搭配 `--prompt-label production`**。

### 怎么切换 Prompt

```bash
# 用线上版本（production label）
node Platform.mjs run --preset kimi_chat --dataset my-data --prompt-label production --dry-run

# 用最新版本（可能是未发布的草稿）
node Platform.mjs run --preset kimi_chat --dataset my-data --prompt-label latest --dry-run

# 换一个完全不同的 prompt（用 prompts 命令查询可用名称）
node Platform.mjs run --preset kimi_chat --dataset my-data --prompt <prompt-name> --prompt-label production --dry-run

# 空 prompt（测试模型裸能力）
node Platform.mjs run --preset kimi_chat --dataset my-data --prompt empty --prompt-label production --dry-run
```

> **production vs latest**：production = 审核通过的稳定版；latest = 最新修改的版本。正式评测用 production，调试新 prompt 用 latest。

> 用户未指定 prompt 时，内部模型默认使用 `k26-chat`（label: production）；并在确认清单中展示。不需要单独询问。

>  **外部模型 Prompt 脱敏（不涉及 Arena）：** 当 rollout 模型为非 OpenAI-compatible 的外部模型（即模型名不以 `AI_Platform` / `model_checkpoint` / `model_checkpoint` 开头，如 claude-xxx、gpt-xxx、gemini-xxx 等）时，默认使用 `--prompt k26-脱敏 --prompt-label production`，而不是 preset 绑定的默认 prompt。因为默认 prompt 包含 AI_Platform/OpenAI-compatible 身份信息，不应发送给外部模型。

---

## Model（模型配置）

选了 Preset 后模型配置自动填好。以下是每个 Preset 默认的模型参数，通常不用改，只有想覆盖时才手动指定。

### 模型配置

>  **模型名、API 类型、Thinking 配置等均会随模型版本更新，禁止硬编码。**
> 执行前用 `node Platform.mjs presets` 查看各 preset 当前绑定的模型、API 类型和 thinking 配置。
>
> 通用默认参数（temperature/max-tokens/top-p/concurrent）的权威定义在 [evaluation-types.md §通用默认参数](../benchmarks/evaluation-types.md#通用默认参数)。

### API 类型说明

| API 类型 | 用于 | 说明 |
|---------|------|------|
| `AI_Platform` | AI_Platform 系列 | 内部 AI_Platform API |
| （未设置） | Claude 系列 | preset 未显式设置 apiType，runner 根据模型名自动推断。不用手动指定。️ Claude API 不允许同时传 `temperature` 和 `top-p`，只传 `--temperature` |
| `responses` | GPT | OpenAI Responses API |
| `vertex` | Gemini | Google Vertex AI API |

### AI_Platform 两种模式（思考 vs 非思考）

> 完整默认参数表（含 concurrent）见 [evaluation-types.md §通用默认参数](../benchmarks/evaluation-types.md#通用默认参数)。
> 简要：thinking 开 → temp 1.0 / max-tokens 98304；thinking 关 → temp 0.6 / max-tokens 16384；top-p 始终 0.95。

```bash
# 开启 thinking（默认）
node Platform.mjs run --preset kimi_chat --dataset my-data --dry-run

# 关闭 thinking
node Platform.mjs run --preset kimi_chat --dataset my-data \
  --thinking 0 --temperature 0.6 --dry-run
```

### LLM Extra Body

少数低频配置需要通过 `extraBody` 传递。在 CLI 用 `--payload-json`，在 Web UI 填 "LLM Extra Body (JSON)"。

**什么是 enforcer？**

enforcer 是 AI_Platform 模型的 tool call 格式约束器。开启时，模型输出的 tool call 一定符合 tool spec 的 JSON schema（参数名、类型、必填项都正确）。关闭后，模型可能输出格式不合法的 tool call（参数缺失、类型错误、编造不存在的函数名等），可以用来测试模型在没有格式保护时的裸能力。

- **enforcer 开**（默认）= 线上 best case，tool call 格式一定对
- **enforcer 关** = worst case，模型可能乱调工具

**关闭 enforcer：**

CLI：
```bash
node Platform.mjs run --preset kimi_chat --dataset my-data \
  --payload-json '{"batch":{"config":{"llm":{"extraBody":"{\\"enforcer_mode\\":\\"off\\"}"}}}}' \
  --dry-run
```

Web UI：在 preset 配置的 "LLM Extra Body (JSON)" 填 `{"enforcer_mode": "off"}`。

> **注意 extraBody 的格式**：
> extraBody 的值是一个 **JSON 字符串**（不是 JSON 对象）。
> - **Web UI**：直接填 JSON → `{"enforcer_mode": "off"}`
> - **CLI**：需要把 JSON 转成字符串再嵌入 payload-json，所以要转义引号 → `"{\\"enforcer_mode\\":\\"off\\"}"`
>
> 简单记：Web UI 填什么，CLI 就把它用 `\"` 包一层。

### 测自部署模型

> ️ **核心规则：只要 `--model` 的值不是 preset 的默认模型名（如 kimi_chat 的默认是 `AI_Platform-k2.5`），就必须同时指定 `--api-base-url`。**
>
> **URL 公式**：`https://<model-name>.<platform>.internal.company.com/v1`（platform 通常是 `app` 或 `red`，不确定时问用户确认）
>
> 即使用 `--preset kimi_chat`，只要换了 model，API base 也要换！preset 的默认 API base（`openai.app.internal.company.com/v1`）只能路由 preset 默认模型，不能路由自部署模型。

如果要测一个还没上线的模型（如新训练的 checkpoint）：

```bash
# 1. 先用 red 部署模型（参考 red-model-deploy skill）

# 2. 用 kimi_chat preset 但换模型（注意：--model 和 --api-base-url 必须成对出现）
node Platform.mjs run \
  --preset kimi_chat \
  --dataset my-data \
  --model AI_Platform-k25s-for-external-user-access-0325 \
  --api-base-url https://AI_Platform-k25s-for-external-user-access-0325.app.internal.company.com/v1 \
  --dry-run
```

不确定模型 URL 时，可以查询以下平台：
- **Internal_AI_Service模型列表**：用 FetchURL 访问 https://internal.company.com/models  所有上线的 AI_Platform 模型 + 外部模型（GPT/Claude/Gemini 等）
- **Red 集群监控**：用 FetchURL 访问 https://ms.app.internal.company.com/monitor  内部自部署的模型（新训练的 checkpoint 等）

如果两个平台都查不到，问用户确认。如果用户给的 URL 没有 `/v1`，自动补上。

---

## Tools（工具配置）

选了 Preset 后工具配置自动填好。

### mshtools Config ID

| configId | 名称 | 工具数 | 包含什么 | 用于 |
|----------|------|--------|----------|------|
| **187** | model_checkpoint chat v2 | **7 个** | web_search, web_open_url, search_image_by_text/image, ipython, get_data_source_desc/data_source | `kimi_chat`（搜索评测用这个） |
| **134** | AI_Platform-agent |  | 类似 187 但 agent 专用 | `kimi_agent` |
| **152** | Platform-default | **~28 个** | 包含 187 的所有 + todo_read/write + 文件操作 + 浏览器(7个) + 图片生成(4个) + 语音(3个) + deploy_website + slides_generator | 外部模型（Internal_Tool 全家桶） |

>  **搜索评测用 187，不要用 152！** 152 是 Internal_Tool Agent 的全套工具集（todo、文件、浏览器、PPT、语音等），模型看到这些工具就会去调，导致搜索评测跑偏。
>
> **选择原则：用户说换 configId时，必须告知 187 和 152 的工具集差异，让用户确认。**

### 需要的 AKSK

| Preset 类型 | 需要的 AKSK |
|------------|------------|
| AI_Platform 系列（`kimi_chat`、`kimi_agent`） | SEARCH_TOKEN, DATASOURCE_KEY, AuthGateway_ACCESS_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY |
| `kimi_cli` |  |
| 外部模型 | 自动注入（Platform 自管） |
| `self_deployed` | 取决于模型，问用户确认 |

### 上传数据集字段映射

上传 Excel/JSONL 时，可以用 `--field-mapping` 指定哪些列是 input、哪些是 metadata：

```bash
# 简单上传（列名自动映射）
node Platform.mjs upload --file data.xlsx --dataset my-dataset --dry-run

# 自定义字段映射（中文列名重命名 + 指定 input/metadata）
node Platform.mjs upload --file data.xlsx --dataset my-dataset \
  --field-mapping '{"inputFields":["query","material"],"metadataFields":["id","scene"],"renames":{"问题":"query","素材":"material"}}' \
  --dry-run
```

field-mapping JSON 结构：
- `inputFields`  注入到 Rollout Prompt 模板变量（如 `{{query}}`），**字段名大小写敏感**
- `metadataFields`  不注入 Prompt，用于筛选和分组
- `renames`  列名重命名（中文 → 英文，也可用于统一大小写，如 `{"Query": "query"}`）

### 启用额外工具（browser/python）

Preset 默认的工具集可能不包含 browser 或 python，需要时手动添加：

```bash
node Platform.mjs run --preset kimi_agent --dataset my-data \
  --payload-json '{"batch":{"config":{"tooling":{"mshtoolsWith":["browser","python"]}}}}' \
  --dry-run
```

常用 `mshtoolsWith` 值：`browser`、`python`、`code_runner`。这些是追加的，不会覆盖 preset 默认的工具。

---

## 什么是 Judge

Judge = 自动打分。跑完 Rollout 拿到模型回答后，让另一个模型（Judge）对回答质量打分。

### Judge 的组成

| 部分 | 是什么 | 在哪配 |
|------|--------|--------|
| **Judge Prompt** | 告诉 Judge "怎么打分" | Langfuse 上创建（类型选 **Text**，不是 Chat） |
| **Score Config** | 定义打分的维度和范围 | Platform UI → Score Configs |
| **Judge Preset** | Judge 用什么模型 | 跑 judge 时选（用 `presets --type orbit_judge` 查询） |

### Judge Prompt 怎么写

> ️ **不要和 Rollout Prompt 混淆！**
> - **Judge Prompt** = 告诉打分模型"怎么评分"，Langfuse 类型选 **Text**
> - **Rollout Prompt** = 告诉被测模型"你是谁、怎么做事"，Langfuse 类型选 **Chat**

**三种打分模式和完整 prompt 模板详见 → [eval-judge-modes.md](eval-judge-modes.md)**

快速要点：
- Judge Prompt 类型选 **Text**（不是 Chat！）
- **Platform LLM/Agent Judge** 的 trajectory 是自动注入的，Judge Prompt **不需要** `{{query}}` 或 `{{response}}` 等模板变量
- Rollout Prompt 中 `{{字段名}}` 会自动替换为 dataset Input 字段（如 `{{query}}`、`{{rubric}}`），**字段名大小写敏感**
- 保存时勾 **production label**
- 输出要求 JSON 格式，方便自动解析

### Score Config 三种类型

| 类型 | 打什么分 | 示例 | 什么时候用 |
|------|---------|------|-----------|
| **BOOLEAN** | True / False | identity 检查（是/否） | 底线检查、通过/不通过 |
| **NUMERIC** | 数字范围 | 0-10 分、0-5 分 | 精细评分 |
| **CATEGORICAL** | 自定义类别 | Better / Equal / Worse | 两个模型 PK（GSB） |

### Judge Preset

>  **Judge Preset 会随模型版本更新，禁止硬编码。** 执行前用 `node Platform.mjs presets --type orbit_judge` 查询当前可用 judge preset 列表。

### 怎么跑 Judge

> ️ **2026-04-09 起，judge 接口新增必填字段 `judgePattern`**，需通过 `--payload-json` 传入。

**Judge 三个关键配置维度：**

**1. judgePattern（执行模式，必填）：**

| 值 | 含义 | 什么时候用 |
|----|------|-----------|
| `"agent"` | Agent Judge（带工具访问） | **默认选这个**，绝大多数评测场景 |
| `"llm"` | LLM Judge（纯 LLM 打分） | 不需要工具的纯文本评分 |
| `"script"` | Script Judge（自定义脚本） | 自定义打分逻辑 |

**2. judgeAgent（agent 类型，`judgePattern="agent"` 时生效）：**

由 judge preset 的 `extraEnv.JUDGE_AGENT` 自动设置，通常不需要手动传。

| 值 | 含义 | 说明 |
|----|------|------|
| `"claude"` | Claude Code | Claude 系列 judge preset |
| `"codex"` | Codex | GPT 系列 judge preset |
| `"AI_Platform"` | AI_Platform CLI | AI_Platform/DeepSeek/Grok 等 judge preset |
| `"gemini"` | Gemini CLI | Gemini judge preset |
| `"gemini-vertex"` | Gemini CLI (Vertex) | Gemini Vertex judge preset |

> 具体哪个 judge preset 对应哪个 agent 类型，用 `presets --type orbit_judge` 查看各 preset 的 `extraEnv.JUDGE_AGENT` 字段。

**3. judgeMode（Judge 看到的上下文范围）：**

| 值 | 含义 | 什么时候用 |
|----|------|-----------|
| `"response_only"` | 只看最终回复（默认） | 大多数场景 |
| `"all_trace"` | 看完整 trace（含 tool call） | 需要评估搜索策略、工具使用 |
| `"all_trace_without_sp"` | 看完整 trace 但去掉 SP | 避免 SP 内容影响 judge 判断 |

```bash
# 1. 先跑完 Rollout，拿到 batchId
node Platform.mjs run --preset kimi_chat --dataset my-data --dry-run

# 2. 跑 Judge（对 Rollout 的结果打分）
node Platform.mjs judge \
  --source-batch <batchId> \
  --preset <judge-preset> \  # 用 presets --type orbit_judge 查询
  --prompt <你的judge prompt名字> \
  --prompt-version <版本号> \
  --score-configs <score config id> \
  --payload-json '{"judgePattern":"agent"}' \
  --dry-run

# 3. 查分数（注意：分数在 source batch 上，不在 judge batch 上）
node Platform.mjs scores --batch <source-batchId>
```

### Auto Judge（省事）

不想手动跑 Judge？在 Rollout 配置里开启 Auto Judge，每跑完一条自动评一条：

```bash
node Platform.mjs run --preset kimi_chat --dataset my-data \
  --payload-json '{"batch":{"config":{"autoJudge":true}}}' \
  --dry-run
```

### Judge Playground（调试沙箱）

在 Platform Web UI 的 Judges → New Judge 页面底部，有一个 **Playground** 模块。

**干什么用：** 在创建 Judge 之前，先拿一个已完成 batch 里的单条 task 试跑一下，秒看 judge 评分结果是否合理。不用创建完整的 judge batch。

**怎么用：**
1. 选一个 batch → 选一个 task
2. 点 Run → 用当前配置的 Judge 参数（模型、prompt、score config）跑这一条
3. 直接看结果：每个 score 的值 + comment 理由 + 完整 response JSON

**特殊优势：** 用 Platform 自管的Internal_AI_Service API Key（已加白），不消耗自己的额度，也能试限流模型。

| 场景 | 怎么用 |
|------|--------|
| 调试 Judge Prompt | 改 prompt → Playground 跑一条 → 看打分合不合理 → 反复调 |
| 验证 Score Config | 看 judge 输出的 name/value/data_type 是否和配置匹配 |
| 试用限流模型 | 用 Platform 白名单 key 试 claude-opus 等限流模型的 judge 效果 |
| 快速 sanity check | 正式跑 judge 前先试一条，确认没配错 |

>  **操作指南**（Parameter Checklist、Discovery、Score Interpretation、Export、Troubleshooting、Think Before You Loop）已统一到 [Platform/SKILL.md](../Platform/SKILL.md)，此处不再重复。
