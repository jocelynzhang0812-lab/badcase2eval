# dwd_chat_group_requestlog_day

## 别名
开放平台请求日志表, API请求日志表, 模型调用日志表, requestlog, requestlog事实表

## 描述
开放平台国内和海外的 request_log 日志表，记录 API 请求明细数据。通过 requestlog_group_id 可判断请求来源（如 AI_Platform-chat, coding, enterprise-tier 等）。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 id（请求唯一标识）
- requestlog_group_id 关键取值：
  - `AI_Platform-chat`/`AI_Platform-chat-anonymous`: C端用户对话
  - `coding`: AI_Platform For Coding (KFC)
  - `enterprise-tier.*`: 开放平台收费用户
  - `maas`: 开放平台MAAS
  - `key-account`: 开放平台KA
  - `free`: 开放平台免费
  - `staff`/`admin`/`intern`: 内部调用
- 典型场景：API请求分析、模型调用统计、来源分析、成本核算、风控审核分析

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dwd_chat_group_requestlog_day | - | - | ODPS 项目 mart_kimi |
| hologres | dwd_chat_group_requestlog_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| id | 请求ID |
| created_at | 请求创建时间 |
| status_ok | 请求成功状态 |
| requestlog_group_id | 产品组ID |
| inference_node_name | 推理节点 |
| segment_labels | 会话标签集合 |
| initial_latency | 准备耗时 |
| total_time_cost | 总耗时 |
| prompt_tokens | 输入Token数 |
| completion_tokens | 输出Token数 |
| cached_tokens | 缓存Token数 |
| mooncake_boosted_tokens | Mooncake增强Token数 |
| total_gpu_time_cost | 总GPU耗时 |
| prefill_gpu_time_cost | 预填充GPU耗时 |
| generation_gpu_time_cost | 生成GPU耗时 |
| input_image_count | 输入图片数 |
| is_seg_source | 是否用户对话 |
| seg_user_id | 对话用户ID |
| query_filter_accepted_list | 输入审核通过列表 |
| query_filter_reasons | 输入审核拒绝原因 |
| response_filter_accepted_list | 回复审核通过列表 |
| response_filter_reasons | 回复审核拒绝原因 |
| response_think_content | 思考内容 |
| kfc_user_id | KFC用户ID |
| kfc_user_agent | KFC用户代理 |
| kfc_user_level | KFC用户等级 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
|推理大模型类别|推理模型分类|CASE WHEN inference_model IS NULL THEN NULL WHEN inference_model LIKE 'mm-small%' THEN 'small' WHEN inference_model LIKE 'mm-large%' THEN 'large' WHEN inference_model LIKE 'mm-medium%' THEN 'medium' WHEN inference_model LIKE 'OpenAI-compatible-x2s%' THEN 'small' ELSE inference_model END|
|产品大类|产品分类-大类|CASE WHEN `requestlog_group_id` IN ('AI_Platform-chat', 'AI_Platform-chat-anonymous') AND `is_seg_source` = 1 THEN 'C端-用户对话' WHEN `requestlog_group_id` IN ('AI_Platform-chat', 'AI_Platform-chat-anonymous') AND `is_seg_source` = 0 THEN 'C端-系统调用' WHEN `requestlog_group_id` IN ('staff', 'admin', 'intern') THEN '内部调用' ELSE 'B端' END|
|产品分类|产品分类-细分|CASE WHEN `requestlog_group_id` IN ('AI_Platform-chat', 'kimi4rec') THEN 'AI_Platform-普通' WHEN `requestlog_group_id` IN ('AI_Platform-videogen', 'community') THEN '其他' WHEN `requestlog_group_id` IN ('AI_Platform-coze') THEN 'AI_Platform-合作' WHEN `requestlog_group_id` IN ('AI_Platform-chat-anonymous') THEN 'AI_Platform-匿名' WHEN `requestlog_group_id` = 'f_mvip' THEN 'AI_Platform-封禁' WHEN `requestlog_group_id` LIKE 'enterprise-tier.%' THEN '开放平台-收费' WHEN `requestlog_group_id` IN ('maas') THEN '开放平台-MAAS' WHEN `requestlog_group_id` IN ('key-account') THEN '开放平台-KA' WHEN `requestlog_group_id` IN ('free') THEN '开放平台-免费' WHEN `requestlog_group_id` IN ('staff', 'admin', 'intern') THEN '内部调用' ELSE `requestlog_group_id` END|
|kimi产品入口|产品入口|CASE WHEN `segment_labels` LIKE '%user_kimiv%' THEN 'kimiv' WHEN `segment_labels` LIKE '%kimi_search%' THEN '普通搜索' WHEN `segment_labels` LIKE '%kimi_search_rag%' THEN 'rag搜索' WHEN `segment_labels` LIKE '%solve_problem_image%' THEN '拍照解题（含task bar）' WHEN `segment_labels` LIKE '%user_writing%' THEN 'app端task bar写作' WHEN `segment_labels` LIKE '%user_translation%' THEN 'app端task bar翻译' WHEN `segment_labels` LIKE '%show_case%' THEN '首页case创建' WHEN `segment_labels` LIKE '%user_math%' THEN 'k1-math' WHEN `segment_labels` LIKE '%tool_img_gen%' THEN '生图tool' WHEN `segment_labels` LIKE '%audio_rtc%' THEN '语音通话' ELSE '其他' END|
|query审核关键词|query审核关键词|concat_ws(',', query_filter_refs)|
|resp审核关键词|resp审核关键词|concat_ws(',', response_filter_refs)|
|query是否被风控|query是否被风控|CASE WHEN array_contains(`query_filter_accepted_list`, '0') THEN '是' ELSE '否' END|
|resp是否被风控|resp是否被风控|CASE WHEN array_contains(`response_filter_accepted_list`, '0') THEN '是' ELSE '否' END|
|是否被风控|是否被风控|CASE WHEN (CASE WHEN array_contains(`query_filter_accepted_list`, '0') THEN '是' ELSE '否' END) = '是' OR (CASE WHEN array_contains(`response_filter_accepted_list`, '0') THEN '是' ELSE '否' END) = '是' THEN '是' ELSE '否' END|
|K2收入|K2收入|CASE WHEN `model_id` IN ('AI_Platform-k2-0711-preview', 'OpenAI-compatible-x3-text-chat') AND `status_ok` = 1 THEN (`prompt_tokens` * 4 - `cached_tokens` * 3 + `completion_tokens` * 16) / 1000000.0 ELSE 0 END|

> **注**：`是否被风控` 依赖于 `query是否被风控` 和 `resp是否被风控`，已展开为完整表达式。若需单独使用中间字段，请参考上面两行的定义。

## 常用字段组合

> ️ **重要**：CSV 格式导出不支持 ARRAY/MAP/STRUCT 等复杂类型，必须使用 `concat_ws(',', array_field)` 转换。下面的字段组合已经处理好所有 ARRAY 字段。

**基础信息**
```sql
dt AS `日期`,
id AS `请求ID`,
conversation_id AS `会话ID`,
trace_id AS `TraceID`,
user_id AS `用户ID`,
response_id AS `响应ID`,
requestlog_group_id AS `产品组ID`,
region AS `地区`,
access_key_id AS `访问密钥ID`,
CASE 
    WHEN `requestlog_group_id` IN ('AI_Platform-chat', 'AI_Platform-chat-anonymous') AND `is_seg_source` = 1 THEN 'C端-用户对话'
    WHEN `requestlog_group_id` IN ('AI_Platform-chat', 'AI_Platform-chat-anonymous') AND `is_seg_source` = 0 THEN 'C端-系统调用'
    WHEN `requestlog_group_id` IN ('staff', 'admin', 'intern') THEN '内部调用'
    ELSE 'B端'
END AS `产品大类`,
CASE 
    WHEN `requestlog_group_id` IN ('AI_Platform-chat', 'kimi4rec') THEN 'AI_Platform-普通'
    WHEN `requestlog_group_id` IN ('AI_Platform-videogen', 'community') THEN '其他'
    WHEN `requestlog_group_id` IN ('AI_Platform-coze') THEN 'AI_Platform-合作'
    WHEN `requestlog_group_id` IN ('AI_Platform-chat-anonymous') THEN 'AI_Platform-匿名'
    WHEN `requestlog_group_id` = 'f_mvip' THEN 'AI_Platform-封禁'
    WHEN `requestlog_group_id` LIKE 'enterprise-tier.%' THEN '开放平台-收费'
    WHEN `requestlog_group_id` IN ('maas') THEN '开放平台-MAAS'
    WHEN `requestlog_group_id` IN ('key-account') THEN '开放平台-KA'
    WHEN `requestlog_group_id` IN ('free') THEN '开放平台-免费'
    WHEN `requestlog_group_id` IN ('staff', 'admin', 'intern') THEN '内部调用'
    ELSE `requestlog_group_id`
END AS `产品分类`,
CASE 
    WHEN `segment_labels` LIKE '%user_kimiv%' THEN 'kimiv'
    WHEN `segment_labels` LIKE '%kimi_search%' THEN '普通搜索'
    WHEN `segment_labels` LIKE '%kimi_search_rag%' THEN 'rag搜索'
    WHEN `segment_labels` LIKE '%solve_problem_image%' THEN '拍照解题（含task bar）'
    WHEN `segment_labels` LIKE '%user_writing%' THEN 'app端task bar写作'
    WHEN `segment_labels` LIKE '%user_translation%' THEN 'app端task bar翻译'
    WHEN `segment_labels` LIKE '%show_case%' THEN '首页case创建'
    WHEN `segment_labels` LIKE '%user_math%' THEN 'k1-math'
    WHEN `segment_labels` LIKE '%tool_img_gen%' THEN '生图tool'
    WHEN `segment_labels` LIKE '%audio_rtc%' THEN '语音通话'
    ELSE '其他'
END AS `产品入口`,
model_id AS `模型ID`,
inference_model AS `推理模型`,
inference_cluster AS `推理集群`,
finish_reason AS `完成原因`,
lang AS `语言`,
small_model_tag_1 AS `小模型一级标签`,
small_model_tag_2 AS `小模型二级标签`,
small_model_tag_3 AS `小模型三级标签`,
request AS `请求内容`,
response AS `响应内容`,
response_think_content AS `思考内容`,
prompt_tokens AS `输入Token数`,
completion_tokens AS `输出Token数`,
cached_tokens AS `缓存Token数`,
mooncake_boosted_tokens AS `Mooncake增强Token数`,
concat_ws(',', query_filter_source_list) AS `输入审核来源`,
concat_ws(',', query_filter_reasons) AS `输入审核原因`,
concat_ws(',', query_filter_content_types) AS `输入审核内容类型`,
concat_ws(',', query_filter_refs) AS `输入审核关键词`,
concat_ws(',', response_filter_reasons) AS `输出审核原因`,
concat_ws(',', response_filter_content_types) AS `输出审核内容类型`,
concat_ws(',', response_filter_refs) AS `输出审核关键词`,
request_tool_content AS `请求工具内容`,
tool_call_id AS `工具调用ID`
```

**ID映射关系**
```sql
id AS `请求ID`,
trace_id AS `TraceID`,
conversation_id AS `会话ID`,
response_id AS `响应ID`,
user_id AS `用户ID`,
seg_user_id AS `对话用户ID`,
access_key_id AS `访问密钥ID`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

**抽样/随机采样查询**
```sql
SELECT * FROM dwd_chat_group_requestlog_day
WHERE dt = '2026-03-01'
  AND ABS(HASH(id)) % 100000 <= 1000
LIMIT 1000
```

**查询多轮对话数据（>=3轮）**
```sql
SELECT *
FROM dwd_chat_group_requestlog_day
WHERE dt = '2026-01-15'
  AND (LENGTH(request) - LENGTH(REPLACE(request, '{"role":"user"}', ''))) / 14 >= 3
LIMIT 1000
```

**查询Claude Code用户数据**
```sql
SELECT *
FROM dwd_chat_group_requestlog_day
WHERE dt = '2026-01-15'
  AND (`user_agent` LIKE '%claude-cli%' 
       OR `user_agent` LIKE '%ClaudeCode%' 
       OR `user_agent` LIKE '%klaude-cli%')
LIMIT 1000
```

## KFC表特殊查询

> **说明**：KFC = AI_Platform For Coding。如果用户查询中提到"kfc"或"coding"，需要增加条件 `requestlog_group_id = 'coding'`。

**识别 AI_Platform For Coding 请求**
```sql
SELECT *
FROM dwd_chat_group_requestlog_day
WHERE dt = '2026-01-15'
  AND `requestlog_group_id` = 'coding'
LIMIT 1000
```

**提取 internal_metadata 中的扩展字段**
```sql
SELECT
    id AS `请求ID`,
    conversation_id AS `会话ID`,
    -- codegw_metadata 是 JSON 字符串，需要两层 GET_JSON_OBJECT 解析
    GET_JSON_OBJECT(GET_JSON_OBJECT(`internal_metadata`, '$.codegw_metadata'), '$.api_format') AS `api_format`,
    GET_JSON_OBJECT(GET_JSON_OBJECT(`internal_metadata`, '$.codegw_metadata'), '$.client_type') AS `client_type`,
    GET_JSON_OBJECT(GET_JSON_OBJECT(`internal_metadata`, '$.codegw_metadata'), '$.client_decision') AS `client_decision`,
    GET_JSON_OBJECT(GET_JSON_OBJECT(`internal_metadata`, '$.codegw_metadata'), '$.user_agent') AS `user_agent`,
    GET_JSON_OBJECT(GET_JSON_OBJECT(`internal_metadata`, '$.codegw_metadata'), '$.user_info.user_id') AS `kimi_user_id`,
    CAST(GET_JSON_OBJECT(GET_JSON_OBJECT(`internal_metadata`, '$.codegw_metadata'), '$.user_info.user_level') AS INT) AS `kimi_user_level`,
    request AS `请求内容`,
    response AS `响应内容`
FROM dwd_chat_group_requestlog_day
WHERE dt = '2026-01-15'
  AND `requestlog_group_id` = 'coding'
LIMIT 1000
```

**按客户端类型筛选（Claude Code等）**
```sql
SELECT *
FROM dwd_chat_group_requestlog_day
WHERE dt = '2026-01-15'
  AND `requestlog_group_id` = 'coding'
  AND GET_JSON_OBJECT(GET_JSON_OBJECT(`internal_metadata`, '$.codegw_metadata'), '$.client_type') LIKE '%claude%'
LIMIT 1000
```
**查询 AI_Platform Claw 请求**
```sql
SELECT *
FROM dwd_chat_group_requestlog_day
WHERE dt = '2026-01-15'
  AND `requestlog_group_id` = 'coding'
  AND `kfc_user_agent` LIKE '%AI_Platform Claw%'
LIMIT 1000
```


**成本统计**
```sql
SELECT
    dt AS `日期`,
    COUNT(*) AS `请求数`,
    SUM(`total_cost`) AS `总成本`,
    AVG(`total_cost`) AS `平均成本`
FROM dwd_chat_group_requestlog_day
WHERE `requestlog_group_id` = 'coding'
  AND dt >= '2026-01-10' AND dt <= '2026-01-15'
GROUP BY dt
ORDER BY dt
```

**排除滥用请求**
```sql
SELECT *
FROM dwd_chat_group_requestlog_day
WHERE dt = '2026-01-15'
  AND `requestlog_group_id` = 'coding'
  AND GET_JSON_OBJECT(GET_JSON_OBJECT(`internal_metadata`, '$.codegw_metadata'), '$.client_decision') != 'REJECT'
LIMIT 1000
```
