# dwd_saas_payment_day

## 别名
SaaS支付明细表, 充值明细表, 开放平台充值表

## 描述
SaaS/开放平台充值/支付明细表，记录每笔充值交易的详细信息，包含支付金额、支付方式、支付状态、退款信息等。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 payment_id（每笔充值唯一）
- 与 dws_saas_account_detail_day 区分：本表是充值交易明细，account 表是用户余额快照
- 与 dws_saas_consume_detail_day 区分：本表是充值（收入），consume 表是消费（支出）

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dwd_saas_payment_day | - | - | ODPS 项目 mart_kimi |
| hologres | dwd_saas_payment_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| payment_id | 支付ID, 充值ID |
| organization_id | 组织ID |
| group_id | 用户组ID |
| auth_type | 认证类型 |
| auth_name | 认证名称, 企业名称 |
| source_region | 支付来源地区 |
| uscc | 统一社会信用代码 |
| amount | 充值金额 |
| payment_type | 支付方式 |
| pay_status | 支付状态 |
| pay_amount | 实付金额 |
| merchant_fee_amount | 手续费 |
| balance | 余额 |
| is_valid_pay | 是否有效充值 |

## 关联关系

本表可与 `dws_saas_account_detail_day` 关联获取用户完整信息：

| 关联表 | 关联字段 | JOIN 类型 | 关系 | 说明 |
|--------|---------|----------|------|------|
| dws_saas_account_detail_day | organization_id + dt | LEFT JOIN | N:1 | 获取组织认证信息、余额等 |

**重要**：关联时必须同时带 `organization_id` 和 `dt` 两个条件。

**JOIN 示例**：
```sql
FROM dwd_saas_payment_day p
LEFT JOIN dws_saas_account_detail_day a 
    ON p.organization_id = a.organization_id 
    AND p.dt = a.dt
WHERE p.dt = '2026-03-12'
```

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
payment_id AS `支付ID`,
organization_id AS `组织ID`,
auth_name AS `认证名称`,
amount AS `充值金额`,
payment_type AS `支付方式`,
pay_status AS `支付状态`
```

**充值明细导出**
```sql
dt AS `日期`,
payment_id AS `支付ID`,
organization_id AS `组织ID`,
group_id AS `用户组`,
auth_type AS `认证类型`,
auth_name AS `认证名称`,
source_region AS `来源地区`,
uscc AS `统一社会信用代码`,
amount AS `充值金额`,
pay_amount AS `实付金额`,
merchant_fee_amount AS `手续费`,
payment_type AS `支付方式`,
pay_status AS `支付状态`,
pay_comment AS `备注`,
time_finish AS `完成时间`,
is_valid_pay AS `是否有效`,
operator AS `操作人`
```

**退款信息导出**
```sql
dt AS `日期`,
payment_id AS `支付ID`,
organization_id AS `组织ID`,
auth_name AS `认证名称`,
amount AS `充值金额`,
refund_id AS `退款ID`,
refund_amount AS `退款金额`,
refund_status AS `退款状态`,
refund_comment AS `退款备注`,
refund_operator AS `退款操作人`,
refund_created_timestamp AS `退款时间`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

**查询某日充值成功记录**
```sql
SELECT 
    payment_id AS `支付ID`,
    organization_id AS `组织ID`,
    auth_name AS `认证名称`,
    amount / 1000000.0 AS `充值金额(元)`,
    payment_type AS `支付方式`,
    pay_status AS `支付状态`,
    time_finish AS `完成时间`
FROM dwd_saas_payment_day
WHERE dt = '2026-03-12'
  AND pay_status = 'success'
LIMIT 1000
```

**查询退款记录**
```sql
SELECT 
    payment_id AS `支付ID`,
    organization_id AS `组织ID`,
    auth_name AS `认证名称`,
    amount / 1000000.0 AS `原充值金额`,
    refund_amount / 1000000.0 AS `退款金额`,
    refund_status AS `退款状态`,
    refund_operator AS `操作人`,
    refund_created_timestamp AS `退款时间`
FROM dwd_saas_payment_day
WHERE dt = '2026-03-12'
  AND refund_id IS NOT NULL
LIMIT 1000
```

[待补充]
