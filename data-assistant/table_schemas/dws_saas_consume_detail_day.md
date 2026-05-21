# dws_saas_consume_detail_day

## 别名
SaaS消费宽表, 开放平台消费表, 消费明细表

## 描述
SaaS/开放平台消费明细宽表，记录每个组织/用户的消费记录，包含产品信息、消费金额、代金券抵扣等。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 无主键（消费明细表，一笔消费一条记录）
- 与 dws_saas_account_detail_day 区分：本表是消费明细（交易级），account 表是用户快照（累计统计）

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_saas_consume_detail_day | - | - | ODPS 项目 mart_kimi |
| hologres | dws_saas_consume_detail_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| organization_id | 组织ID |
| group_id | 用户组ID |
| auth_name | 认证名称, 企业名称 |
| source_region | 数据来源地区 |
| category | 所属分类 |
| access_key_id | AccessKeyID |
| amount | 消费金额 |

## 关联关系

本表可与 `dws_saas_account_detail_day` 关联获取用户完整信息：

| 关联表 | 关联字段 | JOIN 类型 | 关系 | 说明 |
|--------|---------|----------|------|------|
| dws_saas_account_detail_day | organization_id + dt | LEFT JOIN | N:1 | 获取组织认证信息、余额等 |

**重要**：关联时必须同时带 `organization_id` 和 `dt` 两个条件。

**JOIN 示例**：
```sql
FROM dws_saas_consume_detail_day c
LEFT JOIN dws_saas_account_detail_day a 
    ON c.organization_id = a.organization_id 
    AND c.dt = a.dt
WHERE c.dt = '2026-03-12'
```

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
organization_id AS `组织ID`,
auth_name AS `认证名称`,
product_model AS `产品模型`,
amount AS `消费金额`,
voucher_consume AS `代金券消费`,
recharge_consume AS `充值消费`
```

**消费分析导出**
```sql
dt AS `日期`,
organization_id AS `组织ID`,
auth_type AS `认证类型`,
auth_name AS `认证名称`,
group_id AS `用户组`,
source_region AS `数据来源`,
use_case AS `业务场景`,
sector AS `行业`,
product_id AS `产品ID`,
product_type AS `产品类型`,
product_model AS `产品模型`,
product_model_id AS `产品模型ID`,
access_key_id AS `AccessKey`,
amount AS `消费金额`,
voucher_consume AS `代金券消费`,
recharge_consume AS `充值消费`,
erase_amount AS `抹零金额`,
invoice_title AS `发票抬头`
```

**产品分析导出**
```sql
dt AS `日期`,
product_id AS `产品ID`,
product_type AS `产品类型`,
product_model AS `产品模型`,
product_model_id AS `产品模型ID`,
business_type AS `业务类型`,
organization_id AS `组织ID`,
auth_name AS `认证名称`,
amount AS `消费金额`,
voucher_consume AS `代金券消费`,
recharge_consume AS `充值消费`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
