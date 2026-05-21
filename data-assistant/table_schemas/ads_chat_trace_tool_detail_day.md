# ads_chat_trace_tool_detail_day

## 别名
tool, toolnode, 工具调用明细, 对话toolnode明细

## 描述
用于记录对话中工具调用明细的宽表，主要用于分析用户与模型交互过程中工具调用的行为和性能。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 每行代表一次工具调用
- 典型场景：工具调用分析、工具性能监控、工具成功率统计

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | ads_chat_trace_tool_detail_day | - | - | ODPS 项目 mart_kimi |
| hologres | ads_chat_trace_tool_detail_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| user_segment_id | 用户消息ID |
| assistant_segment_id | 模型消息ID |
| user_content | 用户问题 |
| assistant_content | 模型回答 |
| model | 使用模型 |
| request_model_ids | 请求模型列表 |
| msh_provider_id | 模型提供商ID |
| finish_reason | 工具结束原因 |
| tool_cost_time | 工具耗时纳秒 |
| tool_call_function_name | 工具函数名 |
| tool_call_function_arguments | 工具函数参数 |
| tool_status | 工具状态 |

## 计算字段

| 字段名称 | 别名   | 表达式 |
|---------|------|--------|
|场景| 会话场景 |CASE WHEN ARRAY_CONTAINS(request_model_ids, 'OpenAI-compatible-x35-text-free-basic-chat') THEN 'k2d5' WHEN ARRAY_CONTAINS(request_model_ids, 'OpenAI-compatible-x35-think-free-turbo-chat') OR ARRAY_CONTAINS(request_model_ids, 'OpenAI-compatible-x35-think-kpro-turbo-chat') THEN 'k2d5thinking' WHEN model = 'SCENARIO_OK_COMPUTER' THEN 'Internal_Tool' WHEN model = 'SCENARIO_K2' AND (ARRAY_CONTAINS(request_model_ids, 'OpenAI-compatible-x3-think-kfree-turbo-chat') OR ARRAY_CONTAINS(request_model_ids, 'OpenAI-compatible-x3-think-AI_Platform-turbo-chat')) THEN 'K2-think' ELSE '主会话' END|
|工具耗时_秒| 耗时 |`tool_cost_time` * 1.0 / 1000000000|

## 常用字段组合

**基础信息**
```sql
`chat_id` AS `chat_id`,
`user_segment_id` AS `user_segment_id`,
`assistant_segment_id` AS `assistant_segment_id`,
`user_content` AS `用户内容`,
`assistant_content` AS `模型回复内容`,
`trace_id` AS `trace_id`,
`user_id` AS `用户ID`,
`membership_level` AS `会员等级`,
`model` AS `模型`,
`request_model_ids` AS `请求模型ID列表`,
`tool_name` AS `工具名称`,
`msh_provider_id` AS `模型提供商ID`,
`finish_reason` AS `结束原因`,
`tool_cost_time` AS `工具耗时(纳秒)`,
`created_at` AS `创建时间`,
`tool_call_index` AS `工具调用索引`,
`tool_call_type` AS `工具调用类型`,
`tool_call_function_name` AS `工具函数名`,
`tool_call_function_arguments` AS `工具函数参数`,
`tool_status` AS `工具状态`,
`dt` AS `日期分区`
```

**ID映射关系**
```sql
`chat_id` AS `会话ID`,
`user_segment_id` AS `用户SegmentID`,
`assistant_segment_id` AS `模型SegmentID`,
`trace_id` AS `TraceID`,
`user_id` AS `用户ID`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

**查询工具调用成功率**
```sql
SELECT
    (COUNT(CASE when `finish_reason` ='tool_calls' then 1 end)*1.0)/COUNT(1) as `工具调用成功率`
FROM ads_chat_trace_tool_detail_day
WHERE dt = '2026-03-10'
LIMIT 1000
```

**按工具名称统计调用次数和平均耗时**
```sql
SELECT
    `tool_name` AS `工具名称`,
    COUNT(*) AS `调用次数`,
    AVG(`tool_cost_time` / 1000000.0) AS `平均耗时(毫秒)`
FROM ads_chat_trace_tool_detail_day
WHERE dt = '2026-03-10'
GROUP BY `tool_name`
ORDER BY `调用次数` DESC
```
