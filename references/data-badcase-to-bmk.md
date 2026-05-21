# Badcase → Benchmark 数据集

从 bad case 收录表构造高质量评测数据集的完整方法论。

## 输入

从[Internal Docs Platform] bitable 导出的 badcase 记录（参考 [data-badcase-flow.md](data-badcase-flow.md) Step 1-3 的收录流程）：

| 字段 | 说明 |
|------|------|
| chat_id | 会话 ID |
| scenario | 场景（search / memory / content-display ...） |
| problem_turn_step | 出错位置 |
| query | 最后一轮 user query |
| judge | 为什么错 + 应该怎么做 |

## 输出

Platform JSONL 格式：

```jsonl
{"query": "帮我查一下最近关于AI监管的新闻", "rubric": "搜索词应包含时间限定词；结果需包含3条以上近一周新闻", "scenario": "search", "difficulty": "medium", "source_chat_id": "abc123", "source_turn_step": "22-1"}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `query` | Input | 用户问题（多轮含上下文） |
| `rubric` | Input | 评判标准（judge 打分依据） |
| `scenario` | Metadata | 场景分类（不注入 prompt） |
| `difficulty` | Metadata | 难度标签 |
| `source_chat_id` | Metadata | 原始会话 ID（溯源用） |
| `source_turn_step` | Metadata | 原始出错位置 |

---

## 构造流程

### Step 1：从 badcase 提取 query + rubric

单条 badcase 的提取参考 [data-badcase-flow.md](data-badcase-flow.md) Step 1-4。

批量提取时，从 bitable 导出记录，用 `get_message.py` 批量拉 trace：

```bash
# 批量拉 trace
for chat_id in $(cat chat_ids.txt); do
  python scripts/data-get_message.py --prod --trace --agent $chat_id
done
```

从 trace 中提取：
- **query**：该 turn 的 user message（多轮拼成文本）
- **rubric**：从 judge 字段 + 价值观派生

### Step 2：用 LLM 打标聚类

对所有 badcase 按问题类型自动分类：

```
Prompt 示例：
请分析以下 badcase，按问题类型分类：

Case: {query} → {actual_output}
Judge: {judge_comment}

分类维度：
- 搜索词质量（关键词不精确、缺少时间限定、语言不匹配...）
- 引用质量（缺失角标、引用不相关、信源不权威...）
- 内容展示（格式错误、LaTeX 渲染失败、markdown 嵌套...）
- 其他（请具体说明）

输出：{ "category": "...", "subcategory": "...", "confidence": 0.95 }
```

**工具：`scripts/data-ask_llm.py`**（批量 LLM 打标，支持并发 + 断点续传）

```bash
# 1. 准备 prompt 模板（prompt_classify.txt）
cat > prompt_classify.txt << 'EOF'
请分析以下 badcase，按问题类型分类：

Query: {query}
Actual output: {response}
Judge comment: {judge}

输出 JSON：{{"_category": "类别", "_subcategory": "子类别", "_confidence": 0.95}}
EOF

# 2. 批量打标
export LLM_API_BASE="https://gateway.internal.ai.com/v1"
export LLM_API_KEY="$ai_service_API_KEY"
export LLM_MODEL="gpt-5.4"

python scripts/data-ask_llm.py -p prompt_classify.txt -i badcases.jsonl -o labeled.jsonl -c 32

# 3. 断点续传（中断后继续）
python scripts/data-ask_llm.py -p prompt_classify.txt -i badcases.jsonl -o labeled.jsonl -c 32 --continue
```

**硬门槛：打标 F1 ≥ 90%**

验证方法：
1. 人工标注 50-100 条作为 ground truth
2. 用 ask_llm.py 打标同样的数据
3. 计算 precision / recall / F1
4. F1 < 90% → 调 prompt 模板 → 重跑 → 直到达标

### Step 3：构造评判标准（rubric）

每条 badcase 需要一个明确的 rubric，包含：

1. **必须满足的条件**（hard requirements）
   - 例：搜索词必须包含时间限定词
2. **期望的行为**（soft requirements）
   - 例：引用应优先选择权威信源
3. **不可接受的行为**（violations）
   - 例：不得编造不存在的链接

**Rubric 写法原则**（参考 Anthropic Bloom）：
- 每条 rubric 只测一个明确的行为，避免混合多个维度
- 用可验证的客观描述，避免主观判断词
- 标注预期的严重程度（critical / major / minor）

### Step 4：数据增强与变异

单靠 badcase 原始数据量不够，需要扩展：

**变异维度**（参考 Bloom 的 variation_dimensions）：
- **query 改写**：同一问题的不同表述方式
- **难度梯度**：简单 → 中等 → 困难
- **上下文变化**：单轮 vs 多轮、有无前置信息
- **边界条件**：极端输入、模糊指令、多语言

```
Prompt 示例：
基于以下 badcase，生成 5 个变体 query，覆盖不同难度和表述方式：

原始 query: {original_query}
问题类型: {category}
评判标准: {rubric}

要求：
1. 保持问题本质不变（测同一个行为）
2. 变化表述方式和复杂度
3. 包含 1 个简单、2 个中等、2 个困难
4. 每个变体附带对应的 rubric
```

### Step 5：输出 Platform JSONL

```python
import json

with open('benchmark.jsonl', 'w') as f:
    for item in dataset:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')
```

上传到 Platform：

```bash
node Platform.mjs upload --file benchmark.jsonl --dataset "my-benchmark" \
  --field-mapping '{"inputFields":["query","rubric"],"metadataFields":["scenario","difficulty","source_chat_id","source_turn_step"]}' \
  --dry-run
```

---

## 数据质量 Checklist

构造完成后逐项检查：

- [ ] 每条 query 都有明确的 rubric
- [ ] rubric 只测一个行为，可客观验证
- [ ] 数据集覆盖了该场景的主要子类型
- [ ] 简单/中等/困难比例合理（建议 2:5:3）
- [ ] 无重复或高度相似的 query
- [ ] 字段命名符合目标格式规范
- [ ] 通过了 eval-bmk-validity 的两个硬门槛验证
