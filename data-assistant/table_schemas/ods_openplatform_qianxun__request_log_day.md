# ods_openplatform_ai_service__request_log_day

## 别名
Internal_AI_Service请求日志表, ai_service requestlog, 千寻请求日志表

## 描述
Internal_AI_Service（ai_service）平台 API 请求日志明细表，记录Internal_AI_Service平台用户的模型调用详情。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 id（请求唯一标识）
- Internal_AI_Service平台特有字段：`group_id`（用户组）、`sku`（套餐）、`vendor`（供应商）、`cost_cny`（成本）、`credit_usage`（积分消耗）
- 与 `dwd_chat_group_requestlog_day` 区分：本表仅包含Internal_AI_Service平台请求，字段结构更简化
- 与 `dws_saas_requestlog_detail_day` 区分：本表是Internal_AI_Service平台专用，非通用SaaS平台

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | ods_openplatform_ai_service__request_log_day | - | - | ODPS 项目 mart_kimi |
| hologres | ods_openplatform_ai_service__request_log_day | default | ext_mc_holo | Hologres 外表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| id | 请求ID |
| status_ok | 是否成功 |
| http_code | HTTP状态码 |
| type | 请求类型 |
| model_id | 模型ID |
| user_id | 用户ID |
| group_id | 用户组 |
| access_key_id | AccessKey |
| sku | 套餐 |
| vendor | 供应商 |
| cost_cny | 成本（元） |
| credit_usage | 消耗积分 |
| client_ip | 客户端IP |
| client_user | 客户端用户 |
| user_agent | 用户代理 |
| origin_host | 来源域名 |
| trace_id | TraceID |
| path | 请求路径 |
| team | 团队 |
| tag | 标签 |
| prompt_tokens | 输入Tokens |
| completion_tokens | 输出Tokens |
| total_tokens | 总Tokens |
| cached_tokens | 缓存Tokens |
| cache_creation_tokens | 缓存创建Tokens |
| initial_latency | 首token延迟 |
| total_time_cost | 总耗时 |
| finish_reason | 结束原因 |
| stream | 是否流式 |
| n | 生成数量 |
| conversation_id | 会话ID |
| session_id | SessionID |
| request | 请求内容 |
| response | 响应内容 |
| error_detail | 错误详情 |
| display_model_name | 模型显示名 |
| model_ancestor | 模型基版本 |
| provider_id | 提供商 |
| context_cache_id | 上下文缓存ID |
| max_credit | 积分上限 |
| created_at | 请求时间 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**基础信息（快速探查）**
```sql
dt AS `日期`,
id AS `请求ID`,
trace_id AS `TraceID`,
user_id AS `用户ID`,
group_id AS `用户组`,
access_key_id AS `AccessKey`,
model_id AS `模型ID`,
display_model_name AS `显示模型名`,
status_ok AS `是否成功`,
http_code AS `HTTP状态码`,
type AS `请求类型`,
request AS `请求内容`,
response AS `响应内容`,
finish_reason AS `结束原因`,
lang AS `语言`,
prompt_tokens AS `输入Tokens`,
completion_tokens AS `输出Tokens`,
cached_tokens AS `缓存Tokens`,
cost_cny AS `成本（元）`,
credit_usage AS `消耗积分`,
sku AS `套餐`,
vendor AS `供应商`,
client_ip AS `客户端IP`,
origin_host AS `来源域名`,
user_agent AS `用户代理`,
team AS `团队`,
tag AS `标签`
```

**ID映射关系**
```sql
id AS `请求ID`,
trace_id AS `TraceID`,
conversation_id AS `会话ID`,
session_id AS `SessionID`,
user_id AS `用户ID`,
group_id AS `用户组ID`,
access_key_id AS `AccessKeyID`,
context_cache_id AS `上下文缓存ID`
```

**成本分析**
```sql
dt AS `日期`,
user_id AS `用户ID`,
group_id AS `用户组ID`,
model_id AS `模型ID`,
display_model_name AS `显示模型名`,
prompt_tokens AS `输入Token数`,
completion_tokens AS `输出Token数`,
cached_tokens AS `缓存Token数`,
cost_cny AS `成本CNY`,
credit_usage AS `积分消耗`,
max_credit AS `积分上限`,
sku AS `套餐SKU`,
vendor AS `供应商`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

**查询特定用户组的请求**
```sql
SELECT *
FROM ods_openplatform_ai_service__request_log_day
WHERE dt = '2026-04-09'
  AND group_id = 'specific_group_id'
LIMIT 1000
```

**查询特定供应商的请求**
```sql
SELECT *
FROM ods_openplatform_ai_service__request_log_day
WHERE dt = '2026-04-09'
  AND vendor = 'specific_vendor'
LIMIT 1000
```

**成本统计**
```sql
SELECT
    dt AS `日期`,
    vendor AS `供应商`,
    COUNT(*) AS `请求数`,
    SUM(cost_cny) AS `总成本`,
    AVG(cost_cny) AS `平均成本`,
    SUM(credit_usage) AS `总积分消耗`
FROM ods_openplatform_ai_service__request_log_day
WHERE dt >= '2026-04-01' AND dt <= '2026-04-09'
GROUP BY dt, vendor
ORDER BY dt, vendor
```

**查询失败请求**
```sql
SELECT *
FROM ods_openplatform_ai_service__request_log_day
WHERE dt = '2026-04-09'
  AND status_ok = 0
LIMIT 1000
```
