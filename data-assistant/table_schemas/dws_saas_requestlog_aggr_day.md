# dws_saas_requestlog_aggr_day

## 别名
SaaS请求聚合表, 开放平台请求聚合表, API请求聚合表

## 描述
SaaS/开放平台 API 请求聚合表，按组织、模型、AccessKey、Agent等维度聚合的日统计表。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 无主键（聚合表，多维度组合）
- 数据来源：`dws_saas_requestlog_detail_day`
- 与 `dws_saas_requestlog_detail_day` 区分：本表是聚合数据（SUM/COUNT），detail 表是明细数据（单条请求）

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_saas_requestlog_aggr_day | - | - | ODPS 项目 mart_kimi |
| hologres | dws_saas_requestlog_aggr_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| region | 地区 |
| group_id | 用户组ID |
| access_key_id | AccessKeyID |
| saas_tag | SaaS标签 |
| soft_agent | Agent名称 |
| soft_agent_version | Agent版本 |

## 关联关系

本表可与 `dws_saas_account_detail_day` 关联获取用户完整信息：

| 关联表 | 关联字段 | JOIN 类型 | 关系 | 说明 |
|--------|---------|----------|------|------|
| dws_saas_account_detail_day | organization_id + dt | LEFT JOIN | N:1 | 获取组织认证信息、余额等 |

**重要**：关联时必须同时带 `organization_id` 和 `dt` 两个条件。

**与 requestlog_detail 表的关系**：
- 本表是 detail 表的聚合结果（预计算）
- 查询时二选一，无需 JOIN
- 查汇总用 aggr 表，查明细用 detail 表

**JOIN 示例**：
```sql
FROM dws_saas_requestlog_aggr_day r
LEFT JOIN dws_saas_account_detail_day a 
    ON r.organization_id = a.organization_id 
    AND r.dt = a.dt
WHERE r.dt = '2026-03-12'
```

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
region AS `地区`,
organization_id AS `组织ID`,
auth_name AS `认证名称`,
auth_type AS `认证类型`,
model_id AS `模型ID`,
prompt_tokens AS `输入Token数`,
completion_tokens AS `输出Token数`,
total_tokens AS `总Token数`,
session_cnt AS `会话数`
```

**完整字段导出**
```sql
dt AS `日期`,
region AS `地区`,
organization_id AS `组织ID`,
group_id AS `用户组ID`,
auth_type AS `认证类型`,
auth_name AS `认证名称`,
category AS `类别`,
organization_created_date AS `组织创建日期`,
model_id AS `模型ID`,
access_key_id AS `AccessKeyID`,
saas_tag AS `SaaS标签`,
soft_agent AS `Agent名称`,
soft_agent_version AS `Agent版本`,
prompt_tokens AS `输入Token数`,
completion_tokens AS `输出Token数`,
total_tokens AS `总Token数`,
cached_tokens AS `缓存Token数`,
mooncake_boosted_tokens AS `Mooncake加速Token数`,
session_cnt AS `会话数`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
