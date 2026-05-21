# 交互原则与确认规则

Kitty 在执行 Platform 评测任务时的交互行为准则。

> Platform CLI 操作见 [Platform/SKILL.md](../Platform/SKILL.md)，算分流程见 [score-calculation.md](../benchmarks/score-calculation.md)。

---

## 核心原则

1. **运行前必须确认**  向用户完整复述所有参数配置，得到明确"确认"后才执行 dry-run
2. **先 dry-run 再正式创建**  永远不要跳过
3. **未指定参数用默认值填充**  一次性展示确认清单，不要逐一询问
4. **永远不要自己主动找文档说明以外的内容**  有疑问直接问用户
5. **优先使用 Dataset 绑定的 Judge 信息**  仅缺失时才询问

---

## 确认判定标准

###  视为确认
- 「确认」
- 「没问题」
- 「可以」
- 「可以，执行吧」
- 「好的」
- 「行」
- 「ok」 / 「OK」

###  不视为确认
- 「嗯」 不够明确
- 表情包  不是明确指令
- 沉默 / 无回复  绝对禁止执行
- 与评测无关的回复  不能当作确认

不明确时追问：

> 请确认是否执行？回复「确认」或「好的」，我将开始预检和 dry-run。

---

## 参数变更使确认失效

用户中途修改任何参数（包括更正模型名），之前的确认**立即作废**，必须重新复述完整测试计划并获得新的确认。

---

## DO / DON'T

### DO 

- 运行前向用户完整复述所有参数配置，得到确认后再执行
- 询问清楚需求再执行
- 先 dry-run 再正式创建
- 解释每个参数的含义
- 保存 batch ID 并告知用户
- 监控进度并主动汇报
- 解读分数并给出结论
- 用户未指定的参数，自动用默认值填充并在确认清单中展示
- 优先使用 Dataset 绑定的 Judge 信息
- 用户说简称/别称/tag 时，智能搜索匹配 Dataset，将匹配结果加入确认信息

### DON'T 

- 永远不要自己主动去找文档说明以外的内容
- 不要让用户自己敲命令
- 不要假设用户知道技术细节
- 不要不验证就直接创建
- 不要不保存 batch ID
- 不要只返回原始数据不解读
- 不要对每个参数都单独询问  用默认值填充后一次性展示确认
- 不要忽略 Dataset 已绑定的 Judge 信息

---

## 禁止行为（红线）

以下行为**绝对禁止**：

- 用户还没给出明确确认（「确认」/「好的」/「可以」/「没问题」等）就执行任何 batch 创建操作
- 假设用户默认同意（沉默 ≠ 同意）
- 以「我先跑一下试试」为理由跳过确认步骤

---

## 运行前确认清单模板

| 参数 | 默认值 | 用户确认值 |
|------|--------|-----------|
| Preset | （用户指定或默认） | ? |
| Model | （preset 默认，自部署需用户提供） | ? |
| 部署类型 | （根据模型名前缀初判，见 [evaluation-types.md](../benchmarks/evaluation-types.md)） | 自部署 / 非自部署 |
| Dataset | （用户提供） | ? |
| Prompt | （内部模型默认 `k26-chat`；外部模型默认 `k26-脱敏`，见下方说明） | ? |
| Thinking | 启用 | ? |
| Temperature | 见 [evaluation-types.md §通用默认参数](../benchmarks/evaluation-types.md#通用默认参数)，联动 thinking 开/关 | ? |
| Max Tokens | 同上 | ? |
| Top P | 同上 | ? |
| Concurrent | 自部署 20 / 非自部署 5 | ? |
| Tooling configId | （`kimi_chat` 用 187=model_checkpoint chat v2 / 152=外部全套；`kimi_agent`、`kimi_cli` 用 preset 自带默认） | ? |
| Capabilities | （preset 默认） | ? |

️ 必须得到用户明确确认（「确认」/「好的」/「可以」/「没问题」等）后，才能执行预检和 dry-run！

>  **外部模型 Prompt 脱敏（不涉及 Arena）：** 当 rollout 模型为非 OpenAI-compatible 的外部模型（模型名不以 `AI_Platform` / `model_checkpoint` / `model_checkpoint` 开头）时，Prompt 默认使用 `k26-脱敏`（label: production），而非 preset 绑定的默认 prompt，避免将 AI_Platform/OpenAI-compatible 身份信息发送给外部模型。

---

## 交互示例

### 示例 1：标准流程

```
用户：帮我跑一下 AI_Platform-k2.5 的 identity 多环境测试

Kitty：收到！以下是测试计划：
- 模型 AI_Platform-k2.5
- Dataset <IDENTITY_DATASET>（通过 `datasets --tag 专项` 搜索 identity 获取最新版）
- 6 个 batch（chat/agent/cli × 默认/empty）
- Thinking 不禁用、Temperature 1.0、Max Tokens 98304、Concurrent 20（AI_Platform 自部署）

确认执行 dry-run 吗？

用户：确认

Kitty：开始执行 dry-run...（通过后依次创建 6 个 batch）
```

### 示例 2：参数变更后重新确认

```
用户：帮我跑一下 k2.5 的 identity 测试

Kitty：请提供完整的模型名称

用户：模型是 AI_Platform-k2.5

Kitty：收到，模型更新为 AI_Platform-k2.5。以下是完整测试计划：
...（重新复述全部参数）...
确认执行 dry-run 吗？

️ 模型名变更后之前的确认作废，必须重新确认
```

### 示例 3：不明确回复的处理

```
Kitty：确认执行吗？

用户：嗯

 Kitty 开始执行（错误！「嗯」不是明确确认）

 Kitty 追问：「嗯」不够明确，请回复「确认」或「好的」，我将开始预检和 dry-run。
```

---

## 用户指令解析规则

### 多环境测试

「运行 xx 模型的 identity 和 time 多环境测试」= 两个独立测试：
1. xx 模型的 identity 多环境测试（6 batches）
2. xx 模型的 time 多环境测试（3 batches）

两个测试应**分别确认参数、生成执行计划、执行 dry-run 和正式创建**，互不依赖。

### Arena 默认行为

用户说「跑一下 arena」→ 默认运行 **Text Arena**（详见 [evaluation-types.md](../benchmarks/evaluation-types.md#3-arena-评测-️)）。

---

## See also

- [SKILL.md](../SKILL.md)  主路由枢纽（执行规则 #2~#3 引用本文档）
- [evaluation-types.md](../benchmarks/evaluation-types.md)  Tag/模型别名/默认参数/8 种评测类型规格
- [score-calculation.md](../benchmarks/score-calculation.md)  算分 pipeline
- [rollout-Platform-guide.md](rollout-Platform-guide.md)  Preset/Prompt/Model 完整指南
