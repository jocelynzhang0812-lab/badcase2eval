# dws_saas_requestlog_detail_day

## 别名
SaaS请求日志表, 开放平台请求日志表, API请求日志表, SaaS RequestLog

## 描述
SaaS/开放平台 API 请求日志明细表，记录开放平台用户的 API 调用详情，包含请求内容、模型响应、Token消耗、成本等信息。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 id（请求唯一标识）
- 数据来源：`dwd_chat_group_requestlog_day` 过滤后数据（requestlog_group_id LIKE 'enterprise-tier%' OR requestlog_group_id IN ('free', 'key-account', 'staff', 'OpenAI-compatible')
- 与 `dwd_chat_group_requestlog_day` 区分：本表仅包含开放平台/SaaS用户请求，增加了组织信息（organization_id, auth_type, auth_name 等）
- **如果用户没有指定查询SasS时**，不要使用`dws_saas_requestlog_detail_day`

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_saas_requestlog_detail_day | - | - | ODPS 项目 mart_kimi |
| hologres | dws_saas_requestlog_detail_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| id | 请求ID |
| model_id | 模型ID |
| user_id | 用户ID |
| access_key_id | AccessKeyID |
| status_ok | 是否成功 |
| saas_tag | SaaS标签分类 |
| saas_tag_summary | SaaS标签总结 |
| soft_agent | Agent名称 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
|query是否被风控|query是否被风控|CASE WHEN array_contains(query_filter_accepted_list, '0') THEN '是' ELSE '否' END|
|resp是否被风控|resp是否被风控|CASE WHEN array_contains(response_filter_accepted_list, '0') THEN '是' ELSE '否' END|
|是否被风控|是否被风控|CASE WHEN (CASE WHEN array_contains(query_filter_accepted_list, '0') THEN '是' ELSE '否' END) = '是' OR (CASE WHEN array_contains(response_filter_accepted_list, '0') THEN '是' ELSE '否' END) = '是' THEN '是' ELSE '否' END|
|K2收入|K2收入|CASE WHEN model_id IN ('AI_Platform-k2-0711-preview', 'OpenAI-compatible-x3-text-chat') AND status_ok = 1 THEN (prompt_tokens * 4 - cached_tokens * 3 + completion_tokens * 16) / 1000000.0 ELSE 0 END|

> **注**：`是否被风控` 依赖于 `query是否被风控` 和 `resp是否被风控`，已展开为完整表达式。若需单独使用中间字段，请参考上面两行的定义。

## 常用字段组合

**基础信息（快速探查）**
```sql
dt AS `日期`,
id AS `请求ID`,
trace_id AS `TraceID`,
organization_id AS `组织ID`,
auth_name AS `认证名称`,
requestlog_group_id AS `用户组ID`,
model_id AS `模型ID`,
inference_model AS `推理模型`,
status_ok AS `是否成功`,
finish_reason AS `完成原因`,
lang AS `语言`,
prompt_tokens AS `输入Token数`,
completion_tokens AS `输出Token数`,
cached_tokens AS `缓存Token数`,
mooncake_boosted_tokens AS `Mooncake增强Token数`,
CASE WHEN array_contains(query_filter_accepted_list, '0') THEN '是' ELSE '否' END AS `query是否被风控`,
CASE WHEN array_contains(response_filter_accepted_list, '0') THEN '是' ELSE '否' END AS `resp是否被风控`,
access_key_id AS `访问密钥ID`,
client_ip AS `客户端IP`
```

**ID映射关系**
```sql
id AS `请求ID`,
trace_id AS `TraceID`,
conversation_id AS `会话ID`,
session_id AS `SESSION_ID`,
organization_id AS `组织ID`,
user_id AS `用户ID`,
access_key_id AS `访问密钥ID`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
