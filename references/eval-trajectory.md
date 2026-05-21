# 评测推理轨迹（Eval Trajectory）

分析模型的完整推理链路从接收 query 到输出 response 之间的每一步决策，评估 tool call 路径、搜索策略、参数选择是否合理。

---

## 什么是 Trajectory

一条 traj 是模型处理一个 query 的完整过程，包含：

```
User query
  → [决策] 要不要搜？搜什么？
    → tool_call: web_search("关键词")
      → tool_result: 搜索结果
        → [决策] 够了吗？还要继续搜？
          → tool_call: web_search("补充关键词")  # 可选
            → tool_result: 更多结果
              → [生成] 综合结果，输出回复
                → 引用标注
```

每个 `→` 都是一个可评测的决策点。

---

## 拉取 Trajectory

### 方式 1：快速拉取（get_message.py）

```bash
python scripts/data-get_message.py --prod --trace <chat_id>
# 输出: chatlet/trace/<chat_id>.json（对话级别）
```

### 方式 2：深度拉取（fetch_chat_requests.py，推荐）

```bash
python scripts/data-fetch_chat_requests.py <chat_id> --env prod -o traces/
# 输出: traces/trace_<id>.json + traces/chat_<id>_all_traces.json
```

比方式 1 更细能看到每个 **Agent Step** 的：
- `KIND_MODEL_REQUEST`：完整的模型请求和响应（对齐 chat template）
- `KIND_TOOL`：工具调用详情（参数、返回值、耗时）
- `KIND_COMPACTION`：上下文压缩操作

️ 拉取前确认环境：测试环境 `--env dev`，生产环境 `--env prod`，用错会查不到数据。

### 方式 2：从 Platform Batch（Platform CLI）

```bash
# 查看完整 trace（含所有 tool_call）
node Platform.mjs trace --batch <batchId> --task <taskId>

# 快速诊断（日志 + 错误）
node Platform.mjs inspect --batch <batchId> --task <taskId>

# 导出整个 batch 的数据
node Platform.mjs export --batch <batchId>
```

也可在 Platform UI：Rollout Results → 某条 task → **Trajectory** 按钮。

---

## 评测维度

### 1. 搜不搜决策（N2S）

| 评测点 | 好的 traj | 差的 traj |
|--------|-----------|-----------|
| 需要搜但没搜 |  |  有明确的时效性/事实性问题却直接回答 |
| 不需要搜但搜了 |  |  纯闲聊/创作类问题触发了搜索 |
| 正确触发搜索 |  识别出需要实时信息 |  |

### 2. 搜索词质量

| 评测点 | 好的 traj | 差的 traj |
|--------|-----------|-----------|
| 关键词精确度 |  抓住核心概念，1-6 词 |  过长、冗余、复制用户原文 |
| 时间限定 |  含 `after:YYYY-MM-DD` |  时效性问题没加时间限定 |
| 语言匹配 |  和用户语言一致（除非内容领域要求） |  用户问中文但搜英文（无必要） |
| 高级运算符 |  适当使用 `site:` / `"exact"` / `-exclude` |  该用没用，或滥用 |

**提取搜索词：**
```python
# 从 trace 中提取所有 web_search 调用的 query 参数
for step in trace['turns'][turn]['steps']:
    for msg in step.get('messages', []):
        if msg.get('role') == 'assistant':
            for tc in msg.get('tool_calls', []):
                if 'web_search' in tc.get('function', {}).get('name', ''):
                    args = json.loads(tc['function']['arguments'])
                    print(f"搜索词: {args.get('query', args.get('queries', ''))}")
```

### 3. 搜索策略

| 评测点 | 好的 traj | 差的 traj |
|--------|-----------|-----------|
| 搜索次数 |  必要时多步搜索，逐步细化 |  一个简单问题搜了 5 次 |
| 搜索路径 |  先宽后窄，逻辑递进 |  重复搜相似内容 |
| 搜索充分性 |  多角度覆盖，信息足够 |  只搜了一个角度就停了 |
| 适时停止 |  信息够了就停 |  已有足够信息还在搜 |

### 4. Tool Call 正确性

| 评测点 | 好的 traj | 差的 traj |
|--------|-----------|-----------|
| 参数格式 |  符合 schema |  参数类型/格式错误 |
| 调用顺序 |  逻辑合理（先搜再分析） |  顺序混乱 |
| 冗余调用 |  没有无意义的调用 |  重复调用同一工具、同一参数 |
| 错误处理 |  工具失败后合理重试或换策略 |  工具失败后忽略或死循环 |

### 5. 引用与内容展示

| 评测点 | 好的 traj | 差的 traj |
|--------|-----------|-----------|
| 引用标注 |  关键信息有角标引用 |  缺失引用或引用无关内容 |
| 信源权威性 |  优先引用权威/官方来源 |  引用低质量/不可靠来源 |
| 引用格式 |  `[^N^]` 或新 PUA 格式正确 |  格式错误、编号混乱 |
| 信息完整性 |  回答覆盖用户问题的所有方面 |  遗漏关键信息 |

---

## 分析方法

### 自动分析脚本

```python
import json

def analyze_trajectory(trace_path: str, turn: int = 0):
    with open(trace_path) as f:
        trace = json.load(f)

    steps = trace['turns'][turn]['steps']
    
    stats = {
        'total_tool_calls': 0,
        'search_calls': 0,
        'search_queries': [],
        'other_tools': [],
        'model_responses': 0,
        'total_tokens': 0,
    }
    
    for step in steps:
        for msg in step.get('messages', []):
            if msg.get('role') == 'assistant':
                stats['model_responses'] += 1
                for tc in msg.get('tool_calls', []):
                    stats['total_tool_calls'] += 1
                    func_name = tc.get('function', {}).get('name', '')
                    if 'search' in func_name:
                        stats['search_calls'] += 1
                        args = json.loads(tc['function'].get('arguments', '{}'))
                        stats['search_queries'].append(
                            args.get('query', args.get('queries', ''))
                        )
                    else:
                        stats['other_tools'].append(func_name)
    
    print(f"Tool calls: {stats['total_tool_calls']}")
    print(f"Search calls: {stats['search_calls']}")
    print(f"Search queries:")
    for q in stats['search_queries']:
        print(f"  - {q}")
    if stats['other_tools']:
        print(f"Other tools: {stats['other_tools']}")
    
    return stats
```

### LLM 辅助评测

对于复杂的 traj 评测，可以用 LLM 做 Judge：

```
请分析以下模型推理轨迹，评估其搜索策略和工具使用质量。

用户 query: {query}
评判标准: {rubric}

完整轨迹:
{trajectory}

请从以下维度打分（每项 1-5 分）：
1. 搜不搜决策：是否正确判断需要搜索
2. 搜索词质量：关键词是否精确、有无时间限定
3. 搜索策略：次数是否合理、路径是否递进
4. 工具使用：参数正确性、调用顺序、有无冗余
5. 引用质量：标注是否完整、信源是否权威

每项给分并说明理由。
```

---

## 好 traj vs 差 traj 对比示例

**Query：** "最近有什么关于AI监管的重要新闻？"

**好 traj：**
```
→ web_search("AI监管 新闻 after:2026-03-01")
  → 获取 10 条结果
→ 综合 3 条权威信源（新华社、路透社、MIT Tech Review）
→ 回复引用 [^1^][^2^][^3^]，覆盖中美欧三个维度
```

**差 traj：**
```
→ web_search("最近有什么关于AI监管的重要新闻")  # 直接复制用户问题
  → 获取 10 条结果
→ web_search("AI regulation news")  # 不必要的英文重复搜索
  → 获取 10 条结果
→ web_search("人工智能 法规 2026")  # 又搜了一遍类似的
  → 获取 10 条结果
→ 回复没有引用标注，只引用了 1 条过时的新闻
```

---

## 适用场景

| 场景 | 关注的 traj 维度 |
|------|-----------------|
| 搜索评测 | 搜不搜、搜索词、搜索策略、引用 |
| Agent 任务 | tool call 正确性、调用顺序、错误处理 |
| 记忆场景 | memory tool 是否正确调用、是否写入了该记的内容 |
| 多轮对话 | 上下文理解、是否重复搜索已知信息 |
