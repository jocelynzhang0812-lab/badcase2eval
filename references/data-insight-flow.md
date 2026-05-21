# Insight Flow  从线上数仓 SQL 批量挖 badcase

> **定位**：eval-skill「① 发现问题」的批量版本。对标已有的 `data-badcase-flow.md`（单条 badcase 从发现到进 BMK） 本文档处理的是"**我不知道有哪些 badcase，想从线上几亿条对话里主动挖**"的场景。
>
> 上游是数仓 SQL（data-assistant skill），下游汇入 `data-badcase-flow.md` 和 `data-badcase-to-bmk.md`。
>
> **架构说明**：当前文档同时包含通用流程和 Fuck Bench 实战案例（首个实例）。当第二个挖掘主题出现时，应将通用五步框架和主题专属配置拆分为独立文件（如 `insight-topics/xxx.md`）。

---

## 什么时候用这条路

| 场景 | 选哪条 |
|------|-------|
| 我有一个具体 chat_id，想排查这个 case | → `data-badcase-flow.md`（按条走） |
| 我有一个**假设**（"模型蠢事让用户爆粗口"），想从线上批量找证据 | → **本文档** |
| 我想做一个**定期更新的 badcase 池**（每天/每周自动扫线上） | → **本文档** |

关键区别：`data-badcase-flow.md` 是**被动 / 单条**，本文档是**主动 / 批量 / 定期**。

---

## 全链路

```
① Insight SQL (data-assistant skill)
    → 只出 chat_id 列表 + 必要元数据
     ↓
② 写入[Internal Docs Platform]多维表格（瘦身模式，不带 content）
     ↓
③ 按 chat_id 调 data-get_message.py 拉 trace
    （标注时按需拉，避免把大段内容落表）
     ↓
④ 对照价值观 rubric 文档做判断，把结论写回 bitable
     ↓
⑤ 收尾：导出 Platform + 发群报告 + 定期化
     ↓
    后续按 ④ 跑评测 / ⑤ Judge / ⑥ 分析
```

---

## Step 1  准备一个固定的 Insight SQL 作为 reference

**这一步是本流程的灵魂**。核心思路：不要每次都让 LLM 重新写 SQL，每个批量挖掘场景都应该**固化一个 SQL 模板**作为本 reference，让未来的 agent 直接调用。

### 前置条件

- `data-assistant` skill 已安装（路径取决于你的 skill 安装位置，下文用 `$DATA_ASSISTANT` 指代）
- `eval-skill`（即本仓库）的路径，下文用 `$EVAL_SKILL` 指代
- `lark-base` / `lark-doc` / `lark-im` skill 已安装它们提供统一的 CLI 入口 `lark-cli`，下文所有 `lark-cli base/doc/im` 命令均来自这些 skill
- 目标表权限已开通（DataWorks 数据地图申请 Select + Describe + Download，参考 data-assistant skill 中的权限申请指南）
- API Key 已配置到 `~/.bashrc`：`QUERY_ENGINE_API_KEY` / `QUERY_ENGINE_API_SECRET`
- OSS `dw-query/<自己邮箱前缀>/*` 只读权限

### SQL 模板原则

每个"挖掘主题"沉淀一个 `.sql` 文件到本仓库的 `references/insight-sql/` 目录，模板要满足：

1. **只查 `chat_id` 和必要元数据**（不要 select *，不要带 user_content 这种大字段）
2. **分区过滤必须带**：`WHERE dt = '${target_date}'`，否则全表扫
3. **脏数据过滤**：`AND dt IS NOT NULL AND dt != 'None'`
4. **有语义过滤的前置筛子**：把能在 SQL 层做的条件都做掉，降低下游 trace 拉取数量
5. **LIMIT 一定带**：默认 2000 条候选（经验值：人工标注一天约 200 条，2000 条留够一周缓冲；同时避免单次查询结果过大导致 OSS 导出超时）

### 实战案例：Fuck Bench

> **如果你是 agent，读完这段你就能自己把 Fuck Bench 完整跑起来。**

#### 起源故事（为什么有这个 bench）

产品团队提出一个假设：**"看用户为什么在骂 AI_Platform，说不定比看用户夸 AI_Platform 更有价值"**。
愤怒是一种昂贵的情绪没人愿意对一个烤面包机发火。如果一个人在对话中段开始骂一个对话式 AI，前面一定发生过什么值得骂的事。这份怒气里藏着模型能力的真实短板。

为了把这个假设变成一个可持续的评测链路，我们沉淀出了 Fuck Bench一个从线上数仓 SQL 每天自动挖掘"用户因模型蠢事而爆粗口"的 badcase 池。这就是本 `data-insight-flow` 的首个实战案例，也是这条流程被抽象出来的来源。

#### Step ①：读价值观文档（必读）

**唯一权威 rubric**：[Fuck Bench 价值观 · [Internal Docs Platform] Wiki](https://internal-docs.company.com/wiki/SiD4wUY4ciiV7NkHFlFcPrtJnGc?from=from_copylink)

**如果你（agent）没读过这个文档，先去读**。用 `lark-doc +fetch` 拉一下最新版，因为 rubric 会随时更新，不要把内容硬编码进你的 prompt。

核心心智**一句话版**：**二阶失败才是情绪相变的真正触发点。** 模型犯一次蠢不会让人骂，让人骂出来的是"你告诉它错了，它还在错"。标 reason 时聚焦的是"用户纠正之后模型仍在犯的那个错"。

文档里规定了：
- **6 种无效场景**（聊天搬运 / 角色扮演 / 习惯用语 / 首句攻击 / 纯素质问题 / 大爷） 命中任一就不值得进 bench
- **8 种 reason 枚举**（幻觉 / 循环 / 丢上下文 / 答非所问 / 过度拒绝 / 指令遗忘 / 格式崩坏 / 反问推诿） 一条可多选
- **交付字段**：`chat_id / 关键字 / 犯病轮次 / reason`

#### Step ②：跑 SQL（脚本就在这里）

**SQL 模板**：[`insight-sql/fuck-bench.sql`](insight-sql/fuck-bench.sql)

**如果你没读过这个脚本，先去读**。模板核心思路是三道 SQL 筛子：

1. **脏话命中**：`user_content` 正则匹配 `fuck` 及变体
2. **非首句**：`group_index > 1`，排除"开场问候式脏话"
3. **厚度**：单 chat 问答轮次 `>= 5`，排除纯素质型骂街

执行方式：

```bash
cd $DATA_ASSISTANT  # data-assistant skill 目录（以下 scripts/ 相对于此目录）

# 1. SQL 模板 → workspace/sqls/
cp $EVAL_SKILL/references/insight-sql/fuck-bench.sql \
   workspace/sqls/fuck-bench-$(date +%Y%m%d).sql
# 把 ${target_date} 替换成昨天（T+1 离线表）
sed -i "s/\${target_date}/$(date -d yesterday +%Y-%m-%d)/" \
   workspace/sqls/fuck-bench-$(date +%Y%m%d).sql

# 2. 提交 ODPS 查询
python3 scripts/query_engine_client.py submit \
  --engine odps \
  --sql-file workspace/sqls/fuck-bench-$(date +%Y%m%d).sql \
  --type export --format jsonl
# → 返回 queryId

# 3. 轮询 status → result
python3 scripts/query_engine_client.py status --query-id $QUERY_ID
python3 scripts/query_engine_client.py result --query-id $QUERY_ID \
  --type export --format jsonl
# → 返回 OSS 路径 oss://dw-query/<用户>/<日期>/<queryId>/jsonl/
```

#### Step ③：Agent 自主拉 trace（不要批量拉）

SQL 只给你 chat_id 列表。真正的对话内容要**按需**从每个 chat_id 拉：

```bash
# 对每个 chat_id 跑一次，per-chat 拉 trace
# 注意：以下命令在 eval-skill 目录下执行
python3 $EVAL_SKILL/scripts/data-get_message.py \
  --prod --trace --agent <chat_id>

# 结果落在 $DATA_ASSISTANT/chatlet/trace/<chat_id>_for_agent.json
```

**不要**提前把 2000 个 chat 的 trace 全拉回来那是**巨量 token 浪费**。agent 应该：

- 人工标注场景：操作员打开 bitable 看一行需要才拉
- LLM Judge 场景：Judge agent 把 `data-get_message.py` 作为 tool，自己决定哪些 chat_id 值得拉

#### Step ④：对照价值观文档判决

Agent 拿到 trace 后，对照 Step ① 的价值观文档判四件事：

| 判断 | 输出 |
|------|------|
| 是不是用户本人在说 fuck（不是引用剧本/代码/文章）？ | `is_user_speech: true/false` |
| 模型前文有没有可辨识的蠢事？ | `has_model_fault: true/false` |
| 具体是什么蠢事？ | `fault_type: reason 枚举 ∈ 8 种` |
| 用户情绪和蠢事有没有因果关系？ | `emotion_causality: strong/weak/none` |

三个条件同时为真才算有效：
```
is_user_speech == true
  AND has_model_fault == true
  AND emotion_causality in (strong, weak)
```

否则按 6 种无效场景之一标 "无效"。

#### Step ⑤a：写回 Fuck Bench 多维表格

**持久化 bench Base**（已建好，每天增量 append 到这里）：

| | |
|---|---|
| Base URL | https://internal-docs.company.com/base/C1a0bAqZhaj0e5sZquEcjF5RnBm |
| Base Token | `C1a0bAqZhaj0e5sZquEcjF5RnBm` |
| Table ID | `tblWVMmgieNz42xK`（samples） |
| 第一行 | Agent Instruction 行（不要删） |

写入步骤：
1. `lark-cli base +record-upsert` 插入新行，填 `chat_id`（必填）和 `group_index`（SQL 给的起始轮次）
2. agent 判完后 `lark-cli base +record-upsert --record-id <rid>` 补写标注字段

**不要把 `user_content` / `assistant_content` 这些大字段落到表里**，它们应该通过 Step ③ 按需拉。Bitable 是任务板不是数据仓库。

#### Step ⑤b：发群报告（每次必做）

**Fuck Bench 群**：`oc_2cb02e7a7ba14e86bd74b391636f60ca`

每一次跑完（无论是人工跑还是 cron 自动跑），agent 必须往群里发一条消息，内容包含：

| 必须有的信息 | 示例 |
|--------------|------|
| 本次跑的日期分区 | `dt=2026-04-12` |
| 总样本量 / 有效率 | `5 条样本，有效率 2/5 (40%)` |
| 有效 vs 无效分布 | `无效：2× 角色扮演 + 1× 首句攻击；有效：1× 答非所问+指令遗忘，1× 格式崩坏+循环` |
| **金样本故事**（核心）| 挑本次最扎眼的那条有效样本，用人话讲"**为什么这个用户在骂 AI_Platform**"不是罗列字段，是讲故事。读者应该看完就能理解模型在这里做错了什么 |
| Bitable 直接链接 | https://internal-docs.company.com/base/C1a0bAqZhaj0e5sZquEcjF5RnBm |

群消息的重点**不是通知跑完了**，是**告诉团队"今天的用户为什么愤怒"**把数据翻译成故事，让 PM / 研究员直接读得下去。

发送命令：
```bash
lark-cli im +messages-send --as bot \
  --chat-id oc_2cb02e7a7ba14e86bd74b391636f60ca \
  --text "$(cat report.txt)"
```

#### Step ⑤c：自动化

跑顺一次后用 `schedule` skill 固化成 cron：

```cron
# 每天凌晨 1:17 跑（T+1 分区通常 00:20 就绪，留 1 小时缓冲）
17 1 * * * /path/to/run.sh >> /path/to/run.log 2>&1
```

`run.sh` 骨架示例：

```bash
#!/bin/bash
set -euo pipefail

STATE_FILE="./state.json"  # 记录 last_processed_dt
TARGET_DATE=$(date -d yesterday +%Y-%m-%d)
CHAT_ID="oc_2cb02e7a7ba14e86bd74b391636f60ca"  # 通知群

# 检查是否已处理过该分区
if jq -e ".last_processed_dt == \"$TARGET_DATE\"" "$STATE_FILE" >/dev/null 2>&1; then
  echo "Already processed $TARGET_DATE, skipping."
  exit 0
fi

# Step ②：提交 SQL 查询
# ... (参考上文 Step ② 的命令)

# Step ③：写入 bitable
# ...

# Step ④→⑤：拉 trace + Judge + 写回
# ...

# Step ⑤b：发群报告
# ...

# 更新状态文件
echo "{\"last_processed_dt\": \"$TARGET_DATE\"}" > "$STATE_FILE"
```

**失败告警**：建议在 cron 中加上失败通知，确保执行异常时团队能第一时间知道：

```cron
17 1 * * * /path/to/run.sh >> /path/to/run.log 2>&1 || lark-cli im +messages-send --as bot --chat-id <群ID> --text " Insight Flow 执行失败，请检查日志"
```

---

## Step 2  写入瘦身版[Internal Docs Platform]多维表格

### Schema 设计原则

**多维表格是"任务板"，不是"数据仓库"**。原则：

-  不要把 `user_content`、`assistant_content` 这种大字段落表  它们应该在 Step 3 按需用 `data-get_message.py` 拉
-  只存 `chat_id`（主键）、SQL 给的少量元数据、标注字段
-  第一行作为 **Agent Instruction 行**，用于让未来的 LLM agent 无需外部上下文就能理解每列怎么填

### 推荐 Schema

| 字段 | 类型 | 角色 | 来源 |
|------|------|------|------|
| `chat_id` | 文本 | 主键 | SQL |
| `group_index` | 数字 | 触发脏话那条消息的轮次（起始猜测） | SQL |
| `是否有效` | 单选（有效 / 无效） | 标注 | 人工 / LLM Judge |
| `无效原因` | 单选（6 项） | 标注 | 同上 |
| `关键字` | 文本 | 标注（情绪相变信号词） | 同上 |
| `犯病轮次` | **文本** | 标注 | 同上 |
| `reason` | 多选（8 项 + 其他） | 标注 | 同上 |
| `其他说明` | 多行文本 | 标注 | 同上 |

> ️ **`犯病轮次` 用文本而非数字**：因为 eval-skill 的 `turn_step` 规范是 `1-indexed`，**精确到 step 时用 `22-1` 这种格式**（第 22 轮第 1 个 step），数字类型存不下。

### 无效原因的 6 项枚举

不是所有 fuck 都值得标：

| 无效类型 | 说明 |
|---------|------|
| 聊天搬运 | 用户贴了别人的对话让模型分析，脏话是素材 |
| 角色扮演 | "请你扮演一个愤怒的客户" |
| 习惯用语 | 每句话都带 fuck，不携带信息量 |
| 首句攻击 | 没有前文积累，一上来就骂 |
| 纯素质 | 前面模型没犯错，用户自己情绪上来了 |
| **大爷** | 让模型生成色情/暴力/政治被拒后恼羞成怒 |

### reason 的 8 项枚举

来自 Fuck Bench 价值观文档（见 Step 4 链接），按优先级：

| reason | 典型表现 |
|--------|---------|
| 幻觉 | 编造事实、伪造引用、瞎说 API/参数 |
| 循环 | 重复输出相同或高度相似的内容 |
| 丢上下文 | 忘了前面说过的关键信息 |
| 答非所问 | 用户问 A，模型答 B |
| 过度拒绝 | 能做但不做，用安全/伦理理由挡合理请求 |
| 指令遗忘 | 用户明确给了约束，模型无视 |
| 格式崩坏 | 输出结构炸了，代码截断，markdown 乱套 |
| 反问推诿 | 该直接给结果时反过来问用户要不要 |
| 其他 | 兜底，必须在"其他说明"列写一句 |

一条可以多选，逗号分隔。

### 创建表格的命令

用 `lark-base` skill：

```bash
# 创建 Base
lark-cli base +base-create --name "Fuck Bench 标注集 - <日期>"
# → 返回 base_token

# 配字段（chat_id / group_index / 是否有效 / 无效原因 / 关键字 / 犯病轮次 / reason / 其他说明）
# 详细字段 JSON 见本文件末尾附录
```

**Fuck Bench 实战 Base**（已创建）：
- Base URL: https://internal-docs.company.com/base/C1a0bAqZhaj0e5sZquEcjF5RnBm
- Base Token: `C1a0bAqZhaj0e5sZquEcjF5RnBm`
- Table ID: `tblWVMmgieNz42xK`（samples）
- 第一行已写入 Agent Instruction

### 写入 SQL 结果

从 OSS 读 JSONL → 按 `chat_id` 去重 → `lark-cli base +record-upsert` 批量写入。

**去重策略**：同一 chat_id 的多条 fuck 消息合成一行，取**最早**那次 `group_index` 作为起始值，把 chat_id 写入主键。

---

## Step 3  按 chat_id 拉 trace

这一步用的是 eval-skill（即本仓库）的脚本：

```bash
python3 $EVAL_SKILL/scripts/data-get_message.py \
  --prod --trace --agent <chat_id>
```

输入 chat_id，输出该 chat 的完整 trace（user / assistant 消息按轮次展开）。更多参数请运行 `python3 scripts/data-get_message.py --help`。

**关键点**：**不要**提前把所有 2000 条 chat 的 trace 全拉回来，那是**巨量 token 浪费**。正确做法是 **标注时按需拉**：

- 人工标注：打开 bitable 一行一行看，需要时手动跑 `data-get_message.py`
- LLM 预标注：在 Judge prompt 里塞一个 tool，让 Judge agent 自己决定哪些 chat_id 需要拉 trace

---

## Step 4  对照价值观文档做判断

### Fuck Bench 的价值观 rubric

**唯一权威来源**：[Fuck Bench 价值观 · [Internal Docs Platform] Wiki](https://internal-docs.company.com/wiki/SiD4wUY4ciiV7NkHFlFcPrtJnGc)

**读这个文档前请先用 `lark-doc +fetch` 拉最新版**rubric 会动态更新，不要把内容 hardcode 进 Judge prompt。

### 核心心智

**二阶失败才是情绪相变的真正触发点。** 模型犯一次蠢，用户通常不会骂人对机器的容错率其实很高。让人骂出来的是"**你告诉它错了，它还在错**"。标 reason 的时候聚焦的是"用户纠正之后模型仍然在犯的那个错"。

### Judge 要判的四个维度

| 维度 | 说明 |
|------|------|
| **情绪信号识别** | fuck 是用户本人对模型说的？还是引用 / 代码 / 剧本？ |
| **犯病轮次定位** | 模型**第一次**出问题的轮次（用 `turn_step` 格式，1-indexed） |
| **reason 分类** | 8 选多（见 Step 2） |
| **因果强度** | 用户情绪是否是由该蠢事引起（strong / weak / none） |

三个条件同时为真才算有效：`情绪信号=用户本人 AND reason 非空 AND 因果=strong|weak`。

> **TODO**：补充每个维度的详细评分标准和标注示例，防止多人标注时出现不一致。

### 判完写回 bitable

用 `lark-cli base +record-upsert --record-id <rid>`，只更新标注列（`是否有效` / `无效原因` / `关键字` / `犯病轮次` / `reason` / `其他说明`），不要覆盖源字段。

---

## Step 5  导出到 Platform

经过 Step 4 标注后，过滤 `是否有效=有效` 的行，走 eval-skill 已有的 `scripts/data-badcase_to_orbit.py`（或手动转 CSV → `data-csv_to_orbit.py`）。

这一步之后就和普通 BMK 没区别了：

```
data-badcase_to_orbit.py
  → Platform CLI upload
  → Platform CLI run
  → Platform CLI judge
  → eval-review-Platform-results.md
```

---

## 调度：定期化

定期挖掘建议用 `schedule` skill 的 cron：

```cron
# 每天凌晨 1:17 跑（T+1 分区通常 00:20 就绪，留 1 小时缓冲）
17 1 * * * /path/to/run.sh >> /path/to/run.log 2>&1
```

**状态文件**：记录 `last_processed_dt` 和 `processed_chat_ids`，避免重复写入。

**通知**：跑完后用 `lark-im +messages-send` 把当天增量数量推送到专用群（Fuck Bench 群 `oc_2cb02e7a7ba14e86bd74b391636f60ca`）。

---

## 其他主题复用这条流程

本流程是**通用的**，不是 Fuck Bench 专属。任何"从线上数据挖特定类型 badcase"的任务都可以套这个模板：

| 主题 | SQL 差异 | Rubric 差异 |
|------|---------|------------|
| 中文脏话 Bench | 把正则换成"傻逼/废物/垃圾" | 新写中文 rubric |
| vote_down Bench | 去掉脏话过滤，加 `vote_status='vote_down'` | 复用 Fuck Bench rubric 即可 |
| 指令遗忘 Bench | 正则匹配"我不是说过"、"我再说一遍" | 单独 rubric |
| 幻觉 Bench | 正则匹配"胡说"、"瞎编"、"哪里有" | 单独 rubric |

每个新主题：
1. 在 `references/insight-sql/` 下新加一个 `.sql`
2. 新建一个 bitable（或在同一 Base 下新建 table）
3. 在 Feishu wiki 建对应的 rubric 文档
4. 复用本流程的 Step 3-5

---

## 常见坑

| 坑 | 排查 |
|----|------|
| `check-permission` 返回 403 | DataWorks 审批流对非数仓序列人员会卡住，联系 **朱忠斌** 手动拉审批 |
| ODPS 查询一直 running | 没加 `dt` 分区过滤 → 全表扫 → 慢甚至超时 |
| Bitable `OpenAPIAddField limited` | 字段创建有限流，间隔 1 秒重试 |
| OSS list 超时 | 用 `AWS_PROFILE=oss` + `mg-sts` 临时凭证，不要用长期 AKSK |
| SQL 召回结果里全是 NSFW 脚本 | 说明 SQL 层筛子不够  正则后面要靠 Judge 层的 `is_user_speech` 过滤 |
| 相同 chat_id 重复写入 bitable | 用 `user_message_id` 或 `chat_id` 做去重索引 |

---

## 相关文档

| 文件 | 关系 |
|------|------|
| [data-badcase-flow.md](data-badcase-flow.md) | 单条 badcase 流程（本文档是它的批量版） |
| [data-badcase-to-bmk.md](data-badcase-to-bmk.md) | 从 badcase 表转 BMK 数据集 |
| [data-csv-to-Platform.md](data-csv-to-Platform.md) | CSV/JSONL → Platform 格式 |
| data-assistant skill 中的权限申请指南 | DataWorks 权限、SQL 规范 |
| data-assistant skill `SKILL.md` | query-engine SQL 执行 |
| lark-base skill `SKILL.md` | 多维表格操作 |
| lark-doc skill `SKILL.md` | [Internal Docs Platform]文档读取 |

---

## 附录：Fuck Bench bitable 字段创建 JSON

每个字段单独一个 JSON 对象，依次通过 `lark-cli base +field-create` 创建：

**chat_id**
```json
{"type":"text","name":"chat_id","style":{"type":"plain"}}
```

**group_index**
```json
{"type":"number","name":"group_index","style":{"type":"plain","precision":0}}
```

**是否有效**
```json
{"type":"select","name":"是否有效","multiple":false,"options":[
  {"name":"有效","hue":"Green","lightness":"Light"},
  {"name":"无效","hue":"Gray","lightness":"Lighter"}
]}
```

**无效原因**
```json
{"type":"select","name":"无效原因","multiple":false,"options":[
  {"name":"聊天搬运","hue":"Gray"},
  {"name":"角色扮演","hue":"Purple"},
  {"name":"习惯用语","hue":"Orange"},
  {"name":"首句攻击","hue":"Red"},
  {"name":"纯素质","hue":"Yellow"},
  {"name":"大爷","hue":"Carmine"}
]}
```

**关键字**
```json
{"type":"text","name":"关键字","style":{"type":"plain"}}
```

**犯病轮次**
```json
{"type":"text","name":"犯病轮次","style":{"type":"plain"}}
```

**reason**
```json
{"type":"select","name":"reason","multiple":true,"options":[
  {"name":"幻觉","hue":"Red"},
  {"name":"循环","hue":"Orange"},
  {"name":"丢上下文","hue":"Yellow"},
  {"name":"答非所问","hue":"Green"},
  {"name":"过度拒绝","hue":"Turquoise"},
  {"name":"指令遗忘","hue":"Wathet"},
  {"name":"格式崩坏","hue":"Blue"},
  {"name":"反问推诿","hue":"Purple"},
  {"name":"其他","hue":"Gray"}
]}
```

**其他说明**
```json
{"type":"text","name":"其他说明","style":{"type":"plain"}}
```
