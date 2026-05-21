# dws_saas_account_detail_day

## 别名
SaaS用户宽表, 开放平台用户表, 企业用户表

## 描述
SaaS/开放平台用户明细宽表，包含组织/个人用户的信息、认证、财务数据、使用统计等。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 organization_id
- 覆盖认证类型：无认证(none)、个人认证(personal)、企业认证(company)
- 个人认证用户无企业名称和行业信息
- 与 dws_kimi_user_detail_day 区分：本表是开放平台账号体系（API Key用户），非 AI_Platform C端产品用户

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_saas_account_detail_day | - | - | ODPS 项目 mart_kimi |
| hologres | dws_saas_account_detail_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| organization_id | 组织ID |
| group_id | 用户组ID |
| auth_type | 认证类型 |
| auth_name | 认证名称, 企业名称 |
| auth_date | 认证日期 |
| organization_source_region | 组织来源地区 |
| use_case | 业务场景 |
| sector | 行业 |
| cur | 充值余额 |
| voucher_cur | 代金券余额 |
| total_recharge_amount | 累计充值金额 |
| total_recharge_consume | 累计充值消耗 |
| total_voucher_amount | 累计代金券金额 |
| total_voucher_consume | 累计代金券消耗 |
| hold_amount | 冻结金额 |
| organization_is_banned | 组织是否封禁 |
| organization_created_date | 组织创建日期 |
| has_paied | 是否付费 |
| input_tpd | 日输入Token数 |
| output_tpd | 日输出Token数 |
| rpd | 日请求次数 |
| cached_tokens | 日缓存Token数 |
| category | 所属分类 |
| earlist_payment_date | 首充日期 |
| earlist_consume_date | 首消日期 |
| lasted_payment_date | 最近充值日期 |
| lasted_consume_date | 最近消费日期 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
organization_id AS `组织ID`,
auth_name AS `企业名称`,
auth_type AS `认证类型`,
group_id AS `用户组`,
organization_source_region AS `地区`,
has_paied AS `是否付费`
```

**组织信息导出**
```sql
dt AS `日期`,
organization_id AS `组织ID`,
group_id AS `用户组ID`,
auth_type AS `认证类型`,
auth_name AS `认证企业名称`,
auth_date AS `认证日期`,
category AS `分类`,
organization_source_region AS `组织来源`,
use_case AS `业务场景`,
sector AS `行业`,
organization_is_banned AS `是否封禁`,
organization_created_date AS `组织创建日期`,
abstract_user_country_name AS `归因国家`,
abstract_user_country_cn_short AS `归因国家中文`
```

**财务数据导出**
```sql
dt AS `日期`,
organization_id AS `组织ID`,
auth_name AS `企业名称`,
cur AS `充值余额`,
voucher_cur AS `代金券余额`,
total_recharge_amount AS `累计充值`,
total_recharge_consume AS `累计消耗`,
total_voucher_amount AS `累计代金券`,
total_voucher_consume AS `代金券消耗`,
total_voucher_expired_amount AS `代金券过期`,
total_refunded_amount AS `退款金额`,
total_invoiced_amount AS `开票金额`,
hold_amount AS `冻结金额`,
has_paied AS `是否付费`
```

**使用统计导出**
```sql
dt AS `日期`,
organization_id AS `组织ID`,
auth_name AS `企业名称`,
input_tpd AS `日输入Token`,
output_tpd AS `日输出Token`,
rpd AS `日请求次数`,
cached_tokens AS `日缓存Token`,
consume_amount_1d AS `当日消费`,
payment_amount_1d AS `当日充值`,
last_consume_at AS `最后消费时间`,
lasted_payment_date AS `最近支付日期`,
lasted_consume_date AS `最近消费日期`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
