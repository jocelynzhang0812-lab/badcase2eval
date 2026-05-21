# Badcase 链路：发现 → 收录 → 复现 → 进 BMK

从用户发现一个 badcase（拿到 chat_id）到最终进入 BMK 持续观测的完整路径。

支持两种模式：
- **单条模式**：拿到一个 chat_id，走完整 8 步流程
- **批量模式**：一批 chat_ids，先快速筛查哪些是 badcase，再对确认的走后续流程

---

## 前半段：发现 → 收录

### Step 1：拉取完整 context

```bash
# 完整拉取：trace + 用户视角对话 + 用户附件/图片
python scripts/data-get_message.py --prod --trace --conversation --download_file <chat_id>

# 拉取完整轨迹（含 model response、reasoning、tool calls、usage，更详细）
python scripts/data-get_full_trajectory.py <chat_id> --output chatlet/trace/<chat_id>_full.json
```

输出：
- `chatlet/trace/<chat_id>.json`  完整 trace（模型视角：每个 turn-step 的 request/response）
- `chatlet/conversation/<chat_id>.json`  对话记录（用户视角：role=user / role=assistant）
- `chatlet/files/<chat_id>/`  用户上传的附件、图片

> **`--trace` vs `--conversation` 的区别**：
> - `--trace`：模型级别，包含 system prompt、memory 注入、tool_calls、中间 step，用于**深度分析**
> - `--conversation`：用户级别，只有 user/assistant 消息对，用于**快速预览**和**judge 打标**
> - `--download_file`：下载用户上传的附件/图片到本地，多模态 case 必须开启

也支持 share link：
```bash
python scripts/data-get_message.py --prod --trace --conversation --download_file "https://www.AI_Platform.com/share/xxx"
```

拉完后给用户看对话摘要：用户问了什么、模型回了什么、调了哪些工具。如果有附件/图片，展示文件列表。

#### 批量拉取

```bash
# 从文件批量拉取
for id in $(cat chat_ids.txt); do
  python scripts/data-get_message.py --prod --trace --conversation --download_file "$id"
done
```

### Step 1.5：快速预筛（可选，批量时推荐）

> 适用场景：拿到一批 chat_ids（如从数仓 SQL 挖出、从 feedback 数据库导出），需要先筛出哪些值得深入分析。
> 单条明确的 badcase 可跳过此步，直接进 Step 2。

用模型对 `conversation.json` 做快速判定：是否存在明显质量问题？

**执行**：

1. 读取 `chatlet/conversation/<chat_id>.json`（用户视角对话，比 trace 轻量）
2. 如有附件/图片（`chatlet/files/<chat_id>/`），一并提供给多模态模型
3. 用 LLM 快速判定：

```
你是一个产品体验质量审核员。请判断以下对话是否存在明显的质量问题。

## 对话内容
{conversation}

## 输出 JSON
{
  "has_issue": true/false,
  "brief": "一句话描述问题（如无问题则写'无明显问题'）",
  "suggested_scenario": "最可能的场景分类（search/memory/content-display/datasource/other）"
}
```

4. 输出筛查结果清单：

| chat_id | 有问题 | 简述 | 建议场景 |
|---------|--------|------|----------|
| abc123 |  | 搜索结果过时，引用了去年数据 | search |
| def456 |  | 无明显问题 | - |
| ghi789 |  | 上传图片后回复内容与图片无关 | content-display |

5. 过滤出 `has_issue=true` 的 chat_ids，进入 Step 2 深入分析

**批量并发**：可用 `data-ask_llm.py` 的并发引擎处理大量 case：

```bash
# 先把 conversation 整理成 JSONL
python -c "
import json, glob
with open('/tmp/to_judge.jsonl', 'w') as out:
    for f in glob.glob('chatlet/conversation/*.json'):
        chat_id = f.split('/')[-1].replace('.json','')
        msgs = json.load(open(f))
        text = '\n'.join(f'[{m[\"role\"]}]: {m[\"content\"][:500]}' for m in msgs)
        out.write(json.dumps({'chat_id': chat_id, 'conversation': text}, ensure_ascii=False) + '\n')
"

# 用 ask_llm.py 并发打标
python scripts/data-ask_llm.py \
  -p prompts/quick_screen.txt \
  -i /tmp/to_judge.jsonl \
  -o /tmp/screened.jsonl \
  -c 16
```

### Step 2：AI 分析 trace，定位所有问题

> 对 Step 1.5 筛出的（或用户直接给的）badcase chat_id，做**深入分析**。
> 这一步用 `trace`（不是 conversation），因为需要看 tool_calls、中间 step 等细节。

**问用户**对话属于场景几，选取对应价值观文档。

已有价值观（参考 https://internal-docs.company.com/wiki/SwnvwNW9ViXTMLkOzmacqbtqnFe ）：

| 场景 | 价值观 |
|------|--------|
| 搜索 | search-value |
| 内容展示 | content-display |
| 记忆 | memory-value |
| 数据源 | datasource-value |

若涉及多个场景，可询问用户是否需要同时看多个场景的价值观文档。

**执行**：

1. 用 `kitty-feishu` 读取价值观[Internal Docs Platform]文档
2. 读取 trace JSON，逐 turn-step 分析：
   - 该 step 模型做了什么（tool_call、response）
   - 对照价值观，是否违反了某条规则
   - 如果违反：具体违反了什么、应该怎么做才对
3. 如有用户附件/图片（`chatlet/files/<chat_id>/`），结合附件内容分析（如：用户上传了图片但模型回复与图片无关）
4. 找出**所有**违反点，不只是第一个

**展示**：表格形式列出所有问题，让用户确认：

| turn-step | 问题描述 | 违反的价值观 | 严重程度 |
|-----------|----------|-------------|----------|
| 2-1 | 搜索词直接复制用户原文，缺少时间限定 | 搜索词应精简 1-6 词 | major |
| 3-2 | 回复缺少引用角标 | 关键信息须标注引用 | minor |

### Step 3：收录到 badcase 多维表格

确认存在价值观违反后，直接收录：

- **已有多维表格**（之前用过，agent 已知 bitable URL）→ 直接写入，不用问
- **没有多维表格**（首次收录）→ 问用户：
  1. 这个 case 在什么方面违反了什么价值观？
  2. 需要放在哪个多维表格里？（[Internal Docs Platform] bitable URL）

记住用户给的 bitable URL，下次同场景直接写入。

每个人维护自己的 badcase 多维表格，表头：

| 字段 | 类型 | 说明 |
|------|------|------|
| chat_id | 文本 | Chatlet 会话 ID |
| scenario | 文本 | 问题所属场景（search / memory / content-display ...） |
| problem_turn_step | 文本 | 问题首次出现位置，格式 `turn-step`（如 `22-1`），1-indexed |

> **turn_step 两种评测粒度：**
> - **精确到 step**（如 `22-1`）：取该 turn 该 step 的 request messages → API 直打，纯测模型回复质量（无工具）
> - **精确到 turn**（忽略 step）：取该 turn 的完整 messages 作为起点 → Platform 重放，端到端测工具行为（含搜索、tool call）
>
> 选择依据：纯回复质量问题（memory 泄露、文风）用 step 级；涉及工具行为（搜索词质量、tool 参数错误）用 turn 级。
| query | 文本 | 最后一轮 user query（方便辨识，多轮只存最后一轮） |
| judge | 文本 | 一两句话：为什么错 + 应该怎么做才对 |
| 是否加入bmk | 选项 | 默认空，复现验证后标记"是"/"否" |
| repro_dataset | 文本 | 复现验证的 Platform dataset 名（后续导出用，复现后填入） |

**执行**：用 `kitty-feishu` 写入 bitable，追加一行。

如果同一个 chat_id 有多个问题 step，**每个 step 单独一行**。

写入后告知用户：「已收录到 bitable，chat_id: xxx，共 N 个问题点」

#### 批量快速收录（跳过复现验证）

> 适用场景：大批量 badcase 需要先收录进 Platform 数据集，后续统一做复现验证。
> 跳过 Step 4-7，直接把确认的 badcase chat_ids 通过 Platform Lens 批量收录。

```bash
# 把确认的 badcase chat_ids 写入文件
cat > badcase_ids.txt << 'EOF'
abc123
def456
ghi789
EOF

# 通过 Platform Lens 批量收录（服务端自动处理 trace 提取和格式转换）
python scripts/data-orbit_lens_collect.py \
  --dataset "my-benchmark-v1" \
  --from-file badcase_ids.txt

# 也支持 share link
python scripts/data-orbit_lens_collect.py \
  --dataset "my-benchmark-v1" \
  "https://www.AI_Platform.com/share/xxx" "https://www.AI_Platform.com/share/yyy"
```

> **orbit_lens_collect vs trace_to_orbit 的选择**：
> - `orbit_lens_collect`：给 chat_id 就行，服务端处理，**适合大批量快速收录**
> - `trace_to_orbit`：从本地 trace 构造，可选 turn/step、换 system prompt、做 A/B，**适合精细控制**
>
> 如果只是先把 badcase 收进去后续统一处理，用 `orbit_lens_collect`；
> 如果要精确复现某个 turn-step 的问题，走下面的 Step 4-8。

---

## 后半段：收录 → 复现 → 进 BMK

收录完可以紧接着做，也可以攒一批再做。

### Step 4：提取 query + rubric

从 Step 1 拉到的 trace 中提取评测数据。有两种方式：

#### 方式 A：手动提取（精细控制）

**单轮 case**：直接取该 turn 的 user message 作为 query。

**多轮 case**（问题出现在第 N 轮，需要前置上下文才能复现）：

把前置对话拼成文本放在 query 里：

```
[对话历史]
user: 帮我查一下北京天气
assistant: 北京今天晴，最高温度25度...[搜索结果摘要]

[当前问题]
user: 那明天呢？
```

**rubric**：从 Step 2 的分析结果和价值观中提取。格式：「应该怎么做才对」，可客观验证。

输出结构（对齐 `badcase_to_orbit.py` 格式）：

```jsonl
{"query": "用户问题（多轮含上下文）", "rubric": "评判标准", "scenario": "search", "source_chat_id": "abc123", "source_turn_step": "22-1"}
```

#### 方式 B：用 trace_to_orbit.py 自动构造（推荐）

```bash
# 从 trace 自动构造 dataset + Langfuse prompt
python scripts/data-trace_to_orbit.py chatlet/trace/<chat_id>.json \
  --turn <turn_index> \
  --dataset "repro-<chat_id>" \
  --upload
```

`trace_to_orbit.py` 会自动：
- 从 trace 中提取指定 turn 的 messages
- 分离 system_prompt / memory / conversation_history / user_message
- 生成 `orbit_replay/<chat_id>/dataset.jsonl`
- 在 Langfuse 创建对应的 prompt
- `--upload` 时自动上传到 Platform

> **注意 turn_index 映射**：
> - bitable 里的 `problem_turn_step` 是 1-indexed 的 display 编号
> - `trace_to_orbit.py` 的 `--turn` 是 trace 中的 `turn_index`（越大越早）
> - 需要根据 trace JSON 中的 `model_trajectories[].turn_index` 找到对应关系

### Step 5：上传临时数据集

> 如果 Step 4 用了方式 B 的 `--upload`，此步可跳过。

将 Step 4 的数据复制 10 份写入同一个 JSONL 文件，上传为一个 dataset。Platform 每条 item 独立跑一次 rollout，所以 10 条相同数据 = 跑 10 次同样的 query。

```python
import json

item = {"query": "...", "rubric": "...", "scenario": "...", "source_chat_id": "...", "source_turn_step": "..."}
with open("/tmp/repro_temp.jsonl", "w") as f:
    for _ in range(10):
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
```

上传到 Platform：

```bash
node Platform.mjs upload --file /tmp/repro_temp.jsonl \
  --dataset "repro-<chat_id>-<timestamp>" \
  --field-mapping '{"inputFields":["query","rubric"],"metadataFields":["scenario","source_chat_id","source_turn_step"]}' \
  --dry-run
```

️ 展示 dry-run 结果，确认后执行。

### Step 6：复现验证

**问用户**：用哪个 preset？（根据 scenario 建议，如 search → kimi_chat，agent → kimi_agent，最终由用户确认）

```bash
# Dry-run
node Platform.mjs run --preset <preset> --dataset "repro-<chat_id>-<timestamp>" --dry-run

# 确认后执行
node Platform.mjs run --preset <preset> --dataset "repro-<chat_id>-<timestamp>"
```

️ dry-run 后等用户确认。

执行后轮询等待完成：

```bash
node Platform.mjs describe --batch <batchId>
```

完成后 judge 打分。临时 dataset 的 batch 通常没有 auto-judge 配置，需要手动指定参数。

**问用户**：judge preset / prompt / score-configs

```bash
node Platform.mjs judge --source-batch <batchId> --preset <judge_preset> \
  --prompt <prompt_name> --prompt-label production \
  --score-configs <ids> --dry-run
```

️ dry-run 后等用户确认。

### Step 7：判定复现 + 更新状态

查看分数：

```bash
node Platform.mjs scores --batch <batchId>
```

**判定标准**：10 次中 ≥ 1 次不达标（score 低于阈值或 judge 判为 False）→ **确认复现**。

**更新 bitable**：
- 复现 → `是否加入bmk` 标记为 **"是"**，`repro_dataset` 填入临时 dataset 名
- 未复现 → `是否加入bmk` 标记为 **"否"**

告知用户结果：

-  「query "xxx" 复现率 3/10，已确认复现，已标记加入 bmk」
-  「query "xxx" 复现率 0/10，未复现，建议观察或移除」

### Step 8：进入 BMK 持续观测

确认复现的 case，加入正式的 BMK 数据集：

1. 从 bitable 筛选 `是否加入bmk = 是` 的记录，拿到 `repro_dataset` 名
2. 从 repro dataset 导出完整数据（含多轮上下文的 query + rubric）：

```bash
node Platform.mjs export --batch <repro_batchId> --output /tmp/confirmed_case.jsonl
```

3. 从导出数据中提取 input 字段，重新组织成上传格式：

```python
import json

records = []
with open("/tmp/confirmed_case.jsonl") as f:
    for line in f:
        rec = json.loads(line)
        inp = rec.get("traceInput", {})
        records.append({
            "query": inp.get("query", ""),
            "rubric": inp.get("rubric", ""),
            "scenario": rec.get("traceInput", {}).get("scenario", ""),
            "source_chat_id": inp.get("source_chat_id", ""),
            "source_turn_step": inp.get("source_turn_step", ""),
        })

with open("/tmp/to_bmk.jsonl", "w") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
```

4. **定位正式 bmk 数据集名**：

   - 读[Internal Docs Platform]入口页（`G0bcw6CgjioH1Sk8Wo9cjIWxnMb`），找到对应 bench 类型的 subtask 索引
   - 读对应 bench 各 subtask 的设计文档，根据 case 内容判断归属 subtask
   - 从设计文档中获取正式 Platform dataset 名
   - 向用户展示确认：「这条 case 属于 **{bench} / {subtask}**，将追加到数据集 **{dataset}**，是否确认？」
   - 若无匹配 subtask → 建议新建，给出命名建议，等用户确认

5. 上传到正式 bmk 数据集（追加，不覆盖）：

```bash
node Platform.mjs upload --file /tmp/to_bmk.jsonl \
  --dataset "<正式bmk数据集名>" \
  --field-mapping '{"inputFields":["query","rubric"],"metadataFields":["scenario","source_chat_id","source_turn_step"]}' \
  --dry-run
```

️ 确认后执行。

---

## 流程总结

### 单条模式（完整 8 步）

```
chat_id
  │
  ▼
① get_message.py --prod --trace --conversation --download_file <chat_id>
  │  → trace + conversation + 附件/图片
  ▼
② AI 分析 trace（️ 问: 用哪个价值观？）
  │  → 结合附件内容，逐 turn-step 列出所有违反点 → 用户确认
  ▼
③ 写入 bitable（已有表直接写，没有则问用户）
  │
  ▼
④ 提取 query + rubric
  │  → 方式 A: 手动提取
  │  → 方式 B: trace_to_orbit.py 自动构造（推荐）
  ▼
⑤ 复制 10 份 → Platform upload 临时 dataset
  │
  ▼
⑥ Platform run（️ 问: 用哪个 preset？）→ 等完成 → judge
  │
  ▼
⑦ 复现率 ≥ 1/10？
  │  → 是 → bitable 标记"是" → ⑧ 加入正式 bmk dataset
  │  → 否 → bitable 标记"否"
```

### 批量模式（快速筛查 + 批量收录）

```
chat_ids（从数仓/feedback/手动收集）
  │
  ▼
① 批量 get_message.py（拉 conversation + 附件）
  │
  ▼
①.5 模型快速预筛（ask_llm.py 并发打标）
  │  → 输出: 哪些有问题、什么场景
  │
  ├── 有问题的 ──→ ② AI 深入分析（逐条，对照价值观）
  │                    ↓
  │                 ③ 写 bitable
  │                    ↓
  │                 ├── 需要精细复现 → ④⑤⑥⑦⑧（trace_to_orbit 路径）
  │                 └── 先批量收录   → orbit_lens_collect（快速路径）
  │
  └── 无问题的 ──→ 跳过
```

️ = 必须停下来等用户确认的 checkpoint
