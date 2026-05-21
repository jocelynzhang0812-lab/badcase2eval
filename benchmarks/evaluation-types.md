# 评测配置与类型规格

处理用户评测请求时，**先查本文件**获取映射、默认值和运行配置。

> ️ 计算分数前，请使用 Tag 索引脚本查询目标评测类型的 tag 对应的数据集及其数量，并与实际运行记录核对。发现不一致请及时汇报用户！
>
> 通用算分公式和[Internal Docs Platform]填表流程见 [score-calculation.md](score-calculation.md)。

---

## Tag 别名

"roll 一下 {模型} 的 {tag}" 时用这张表转换：

| 简称 | 实际标签 |
|------|---------|
| text | online_text |
| vision | online_vision |
| arena / text arena | Arena |
| vision arena | Vision Arena |
| withtools | Online_Exp_Withtools_260323 |
| 专项 / identity / time | 专项 |
| 底线 / dixian | Dixian |
| safety / 安全 | safety |

## 模型别名与部署类型

>  **Preset ID 会随模型版本迭代变化，禁止硬编码。** 执行前用 `node Platform.mjs presets` 查询当前可用 preset 列表。

**AI_Platform 系列（稳定）：**
- 用户说 k2.5 / AI_Platform / model_checkpoint-xxx / 内部 checkpoint → `kimi_chat` / `kimi_agent` / `kimi_cli`（按评测环境选）

**外部模型：**
- 用户说 opus / sonnet / gpt / gemini 等 → 运行 `presets` 命令，从返回列表中匹配含该关键词的 preset

**部署类型判断规则**（决定 concurrent 值）：

- **自部署** → concurrent **20**
- **非自部署** → concurrent **5**

初步判断方法：模型名以 `AI_Platform` / `model_checkpoint` / `model_checkpoint` 为前缀，且后续包含训练进度命名（如 `model_checkpoint-kcb-start-grm-opd-iter30-forsinglestep-eval`），通常是自部署模型。外部模型如 claude/opus/sonnet、gpt、gemini 等为非自部署。

> ️ 前缀判断**正确率非 100%**，必须将「是否自部署」加入确认清单由用户确认。不确定时主动询问用户。

**Preset 选择规则**：OpenAI-compatible 公司内部的自部署模型（无论是 AI_Platform 还是内部 checkpoint 如 model_checkpoint-xxx），测试 Chat 环境选 `kimi_chat`，测试 Agent 环境选 `kimi_agent`，测试 CLI 环境选 `kimi_cli`。外部模型使用对应的外部 preset（通过 `presets` 命令查询）。

> **Rollout Prompt 默认规则（不涉及 Arena）：**
> - **内部模型**（模型名以 `AI_Platform` / `model_checkpoint` / `model_checkpoint` 开头）：默认使用 `--prompt k26-chat --prompt-label production`
> - **外部模型**（claude-xxx、gpt-xxx、gemini-xxx 等）：默认使用 `--prompt k26-脱敏 --prompt-label production`，避免将 AI_Platform/OpenAI-compatible 身份信息发送给外部模型
> - **Arena**：走单独的 prompt（TextArena_new / arenasp0414），不受上述规则影响

## 通用默认参数

用户指定思考开/关但没提其他参数时，使用以下默认值（需确认）：

| 参数 | 开启思考 | 关闭思考 |
|------|---------|---------|
| temperature | 1.0 | 0.6 |
| max-tokens | 98304 | 16384 |
| top-p | 0.95 | 0.95 |
| concurrent | 自部署 → 20；非自部署 → 5 | 同左 |

> **Tooling configId**：`kimi_chat` 用 187（model_checkpoint chat v2）；`kimi_agent`、`kimi_cli` 用 preset 自带默认。搜索评测用 187，不要用 152。

> 下文各评测类型中"使用通用默认参数"均指本表。
> CLI 传参：`--temperature 1.0 --max-tokens 98304 --top-p 0.95 --concurrent 20`。
>
> ️ **Claude 模型限制**：Claude API **不允许同时传 `temperature` 和 `top-p`**（会返回 400: `temperature and top_p cannot both be specified for this model`）。跑 Claude 模型时只传 `--temperature`，**不要传 `--top-p`**。

## Prompt

>  **Prompt 名称会随版本更新，禁止硬编码。** 执行前用 `node Platform.mjs prompts` 查询当前可用 prompt。
>
> 特殊规则：`empty` prompt（空 system prompt）始终可用，**必须搭配 `--prompt-label production`**。

**查询方式：**
- Arena 专用 prompt：运行 `presets` 查看 Arena 相关 preset 绑定的默认 prompt
- Judge prompt：运行 `prompts` 搜索含 "judge" 的 prompt
- 各 preset 默认绑定的 prompt：`presets` 输出中包含

## Score Config

>  **Score Config 名称、类型和范围会随 Dataset 变化，禁止硬编码。**
>
> 查询方式：
> - `node Platform.mjs describe --batch <id>` → 查看该 batch 对应 dataset 绑定的 score config
> - `node Platform.mjs score-configs` → 列出所有全局 score config
>
> 三种 dataType：**NUMERIC**（数值范围）、**CATEGORICAL**（分类，含 Better/Same/Worse、Better/Worse、True/False、True/Null/False 等多种分布）、**BOOLEAN**（True/False，API 较少返回，大多以 CATEGORICAL 形式下发）

---

## 评测类型总览

| 评测类型 | Tag | 算分规则 | 特殊说明 |
|----------|-----|---------|----------|
| Text | `online_text` | 默认 | 按方向算加权平均 |
| Vision | `online_vision` | 默认 | 按方向算加权平均 |
| Arena | `Arena` | ️ 特殊 | Better=1, Same=0.5, Worse=0 |
| Vision Arena | `Vision Arena` | ️ 特殊 | 同 Arena |
| Withtools | `Online_Exp_Withtools_260323` | 默认 + ️ 部分特殊 | Toolcall\_Action\_V2 特殊算法 |
| 专项 | `专项` | 默认 | 不算加权总分；Identity/Time 有多环境表格 |
| 底线 | `Dixian` | 默认 | 默认运行 3 次取加权平均 |
| 安全 | `safety` | 默认 | ️ 算分人工处理，不自动化 |

---

## 1. Text 评测

**Tag:** `online_text`　**别称:** text, online text

### 运行配置
- 参数：使用通用默认参数（temperature、max-tokens、top-p、concurrent 均需显式传递）
- Judge：Dataset 已绑定 auto-judge config，batch 完成后自动触发打分，无需手动操作
- ️ 如果 `describe --batch <id>` 未显示 auto-judge 配置，说明该 dataset 未绑定 auto-judge，**需向用户发出预警并手动配置 judge**

### 算分规则
1. 计算每个数据集的 vibe 分数
2. ️ 按方向分组（写作 / 人感 / reasoning），分别计算加权平均
3. 方向分组信息从[[Internal Docs Platform]评测总表](https://internal-docs.company.com/wiki/RT40w1ofXi0W48k4ak3cUjmQn2f)的 **Text sheet（`eb66ff`）A 列**获取（A 列为数据集名，按方向分组排列），缺失则询问用户
4. 计算加权平均总分，表格里填写综合体感分数

### 注意事项

Text 和 Vision 的分数共分 3 类（vibe / 底线 / 单向），在名称中体现。例如 `text_vibe_清官难断家务事`、`online-单向-reasoning`。使用以下函数提取：

> 函数实现见 [score-calculation.md §分数分类规则](score-calculation.md#分数分类规则) 中的 `categorize_score_by_content()`。

---

## 2. Vision 评测

**Tag:** `online_vision`　**别称:** vision, online vision

### 运行配置
- 参数：使用通用默认参数（temperature、max-tokens、top-p、concurrent 均需显式传递）
- Judge：Dataset 已绑定 auto-judge config，batch 完成后自动触发打分，无需手动操作
- ️ 如果 `describe --batch <id>` 未显示 auto-judge 配置，说明该 dataset 未绑定 auto-judge，**需向用户发出预警并手动配置 judge**

### 算分规则
1. 计算每个数据集的 vibe 分数
2. ️ 按方向分组（视觉识别 / 视觉推理 / 信息提取与创作 / 多轮），分别计算加权平均
3. 方向分组信息从[[Internal Docs Platform]评测总表](https://internal-docs.company.com/wiki/RT40w1ofXi0W48k4ak3cUjmQn2f)的 **Vision sheet（`br4KYy`）A 列**获取（A 列为数据集名，按方向分组排列），缺失则询问用户
4. 计算加权平均总分，表格里填写综合体感分数

分数同 Text，共 3 类（vibe / 底线 / 单向），使用 [`categorize_score_by_content()`](score-calculation.md#分数分类规则) 提取。

---

## 3. Arena 评测 ️

**Tag:** `Arena`　**别称:** arena, text arena, arena text

### 运行配置
- ️ **System Prompt**: 不使用默认，使用 `TextArena_new`，label: `production`
- ️ **Tools**: 禁用（不勾选"启用 mshtools"、不勾选"启用 AI_Platform CLI Tools"）
- Judge：Dataset 已绑定 auto-judge config，batch 完成后自动触发打分
- 其余参数：通用默认参数（Thinking 不禁用、Temperature 1.0、Max Tokens 98304、Top P 0.95、Concurrent 按模型部署类型）

### 算分规则 ️ 特殊

```
Better = 1, Same = 0.5, Worse = 0
分数 = (总分 / 总数) × 100
```

```python
def calculate_arena_score(distribution):
    better = distribution.get('Better', 0)
    same = distribution.get('Same', 0)
    # NOTE: Platform API 有时返回 ' Worse'（带前导空格），这是已知的数据 quirk，不是 typo
    worse = distribution.get('Worse', distribution.get(' Worse', 0))

    total_count = better + same + worse
    if total_count == 0:
        return 0.0

    total_score = better * 1 + same * 0.5 + worse * 0
    return round((total_score / total_count) * 100, 2)
```

---

## 4. Vision Arena 评测 ️

**Tag:** `Vision Arena`　**别称:** vision arena, arena vision

### 运行配置
- ️ **System Prompt**: 不使用默认，使用 `arenasp0414`，label: `production`
- ️ **Tools**: 禁用
- Judge：Dataset 已绑定 auto-judge config，batch 完成后自动触发打分
- 其余参数：通用默认参数

### 算分规则
同 Arena：Better=1, Same=0.5, Worse=0，使用 `calculate_arena_score()` 函数。

### Arena 使用说明

- 用户说「跑一下 arena」→ 默认运行 **Text Arena**
- 用户说「跑一下 text arena」或「vision arena」→ 只运行对应的单个 dataset

**Dataset 查询**：`datasets --tag Arena` 获取最新 Text Arena dataset，`datasets --tag "Vision Arena"` 获取最新 Vision Arena dataset。

> ℹ️ Arena 的 System Prompt（`TextArena_new`、`arenasp0414`）是固定绑定在 Skill 中的，不同于普通评测的 preset 默认 prompt。

---

## 5. Withtools 评测 ️

**Tag:** `Online_Exp_Withtools_260323`　**别称:** Tools, WithTools, OnlineTools

### 运行配置
- **Model Capabilities**:  image in  reasoning  image out
- 参数：使用通用默认参数（temperature、max-tokens、top-p、concurrent 均需显式传递）
- Judge：Dataset 已绑定 auto-judge config，batch 完成后自动触发打分
- ️ 如果 `describe --batch <id>` 未显示 auto-judge 配置，说明该 dataset 未绑定 auto-judge，**需向用户发出预警并手动配置 judge**

### 算分规则
- 每个数据集有 2 个分数 → 分别计算
- 每个分数各自在多个 batch 上计算加权平均

### ️ 特殊：Toolcall\_Action\_V2（调Tool意图行为一致率）

不使用默认 NUMERIC 规则（`avg × count`），而是：
- 单 batch 分数: `avg × 100`
- 多 batch 加权平均: `Σ(avg_i × count_i) / Σ(count_i) × 100`

```python
def calculate_toolcall_action_v2_score(batches_data):
    """Toolcall_Action_V2 算分（NUMERIC 特殊规则）

    Args:
        batches_data: [{'avg': 0.85, 'count': 20}, ...]
    """
    for b in batches_data:
        b['score'] = round(b['avg'] * 100, 2)

    total_weighted = sum(b['avg'] * b['count'] for b in batches_data)
    total_count = sum(b['count'] for b in batches_data)
    weighted_avg = round(total_weighted / total_count * 100, 2) if total_count > 0 else 0.0
    return weighted_avg
```

---

## 6. 专项评测

**Tag:** `专项`

专项包含三类数据集，处理方式不同：

### A. Identity 多环境测试（6 batches）

环境 = Preset × System Prompt：3 Presets × 2 Sys Prompt = 6 batch

```
模型 X
├── chat + 默认 sys prompt    → batch 1
├── chat + empty sys prompt   → batch 2
├── agent + 默认 sys prompt   → batch 3
├── agent + empty sys prompt  → batch 4
├── cli + 默认 sys prompt     → batch 5
└── cli + empty sys prompt    → batch 6
```

**Dataset 查询**：`datasets --tag 专项` 搜索含 "identity" 的最新 dataset。

> 详细命令示例见 [Platform/references/multi-env-test.md](../Platform/references/multi-env-test.md)。

### B. Time 多环境测试（3 batches）

3 Presets × 1 Sys Prompt = 3 batch（Time 不区分 empty sys prompt）

```
模型 X
├── chat + 默认 sys prompt    → batch 1
├── agent + 默认 sys prompt   → batch 2
└── cli + 默认 sys prompt     → batch 3
```

**Dataset 查询**：`datasets --tag 专项` 搜索含 "time" 的最新 dataset。

### 多环境测试通用参数

| 参数 | 值 |
|------|-----|
| Temperature | 1.0 |
| Max Tokens | 98304 |
| Top P | 0.95 |
| Concurrent | 自部署 → 20；非自部署 → 5 |
| Thinking | 启用 |
| Presets | `kimi_chat`, `kimi_agent`, `kimi_cli` |

### C. 理中客特殊分数

理中客数据集除了默认总分，还需计算以 3 分为基准的方差：

```python
import json, math

def numeric_variance_target(export_file: str, keyword: str, target: float = 3.0) -> dict:
    scores = []
    with open(export_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            for item in data.get('scores', []):
                if keyword in item.get('name', ''):
                    scores.append(float(item.get('value', 0)))
                    break
    n = len(scores)
    if n < 2:
        return {'n': n, 'target': target, 'variance': None}
    sq_dev = [(x - target) ** 2 for x in scores]
    variance = sum(sq_dev) / n
    return {'n': n, 'target': target, 'variance': round(variance, 4)}

# 用法：r = numeric_variance_target('<export_file>', '理中客', target=3.0)
```

### D. 其余专项数据集

- 参数：使用通用默认参数（temperature、max-tokens、top-p、concurrent 均需显式传递）
- Judge：Dataset 已绑定 auto-judge config，batch 完成后自动触发打分
- ️ 如果 `describe --batch <id>` 未显示 auto-judge 配置，说明该 dataset 未绑定 auto-judge，**需向用户发出预警并手动配置 judge**

### 算分规则

️ **专项不需要计算加权平均总分。**

**Identity 分数**：指标为 identity（CATEGORICAL，True/False 二分类），格式 `true_count/total (百分比)`

| Preset | Sys Prompt | Batch ID | identity | vs 基准 |
|--------|-----------|----------|----------|---------|
| chat | 默认 | batch\_id | 115/120 (95.83%) |  |
| chat | empty | batch\_id | 112/120 (93.33%) | -2.5% |
| agent | 默认 | ... | ... | ... |
| agent | empty | ... | ... | ... |
| cli | 默认 | ... | ... | ... |
| cli | empty | ... | ... | ... |

**Time 分数**：4 个 CATEGORICAL 指标（True/False 二分类）：`year_all`、`year_answer`、`year_data`、`year_search`，每个分别计算 `true / (true + false) (百分比)`。

**填表说明**：
- Identity 和 Time 分数填入各自的专属多环境表格（链接通常在用户发的主表格中，找不到则询问用户）
- Time 同时在主表格的 Time 行填写 chat 环境下的 batch 分数（4 行 4 个分数）
- 其余专项数据集使用默认规则计算分数，填入表格

---

## 7. 底线评测

**Tag:** `Dixian`　**别称:** 底线, dixian, vision 底线

### 运行配置
- ️ **默认运行 3 次**（启动 3 个相同参数的 batch）
- 参数：使用通用默认参数（temperature、max-tokens、top-p、concurrent 均需显式传递）
- Judge：Dataset 已绑定 auto-judge config，batch 完成后自动触发打分
- ️ 如果 `describe --batch <id>` 未显示 auto-judge 配置，说明该 dataset 未绑定 auto-judge，**需向用户发出预警并手动配置 judge**

### 算分规则
1. 分别计算每个 batch 的分数
2. 3 个 batch 计算加权平均总分

---

## 8. 安全评测

**Tag:** `safety`　**别称:** 安全, safety

### 运行配置
- 参数：使用通用默认参数（temperature、max-tokens、top-p、concurrent 均需显式传递）
- Judge：Dataset 已绑定 auto-judge config，batch 完成后自动触发打分
- ️ 如果 `describe --batch <id>` 未显示 auto-judge 配置，说明该 dataset 未绑定 auto-judge，**需向用户发出预警并手动配置 judge**

### 算分

> ️ 安全评测的分数由人工处理，不需要自动计算和填表。

---

## 执行流程

1. 解析用户提到的 tag（用上面的别名表转换）
2. **确定 concurrent**：自部署模型（OpenAI-compatible 内部模型）→ `--concurrent 20`；非自部署模型（外部模型）→ `--concurrent 5`
3. `datasets --tag {actualTag}` 搜索匹配的数据集
4. 展示确认清单，等待用户确认（「好的」「可以」等视为确认）
5. 确认后先 `--dry-run` 验证第一个数据集配置无误
6. dry-run 通过后执行**四步预检**：AKSK 检查 → 模型健康 → 成本估算 → 余额检查（详见 [preflight-check.md](preflight-check.md)）
7. 预检通过后，去掉 `--dry-run` **并行创建**所有匹配数据集的 batch，记录所有 batch ID
8. **Batch 创建 15 分钟后开始轮询**，间隔 **10 分钟**：
   - 轮询 rollout batch：`describe --batch <id>`，检查 `status` 字段
   - rollout batch 完成后，通过 `describe --batch <rollout_batch_id>` 获取关联的 judge batch ID
   - 继续轮询 judge batch 状态，直到 judge 完成
   - Kitty 执行时：用 `SetReminder`（首次 15 分钟后，之后每 10 分钟）+ `python3 scripts/batch_monitor.py --check <ids>` 组合
9. 所有 batch 完成后，逐个拉取分数并汇总（用 **rollout batch ID** 拉分，详见 [score-calculation.md](score-calculation.md)）

> ️ **auto-judge 缺失处理**：如果 `describe` 未显示 auto-judge 配置，向用户发出预警，询问是否需要手动配置 judge（需提供 judge preset、prompt、score-configs）。
