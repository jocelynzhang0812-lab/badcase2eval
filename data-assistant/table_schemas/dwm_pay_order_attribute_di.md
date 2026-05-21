# dwm_pay_order_attribute_di

## 别名
订单归因表, 支付订单归因表, 订阅归因表

## 描述
订单归因表，记录支付订单的完整归因链路，包括支付前后的对话场景、模型使用情况、页面入口来源等，用于分析订阅事件的渠道来源和用户转化路径。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 order_id（订单唯一标识）
- 与 dwd_pay_order_day 区分：本表聚焦订单的归因分析（渠道来源、对话场景），dwd_pay_order_day 聚焦订单本身的支付信息
- 典型场景：订单来源分析、转化漏斗分析、渠道效果评估、用户付费路径分析

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dwm_pay_order_attribute_di | - | - | ODPS 项目 mart_kimi |
| hologres | dwm_pay_order_attribute_di | default | ext_mc_holo | Hologres 加速表 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| show_enter_method | 套餐页展现入口 |
| select_enter_method | 套餐选择入口 |
| pay_show_enter_method | 支付页展现入口 |
| pay_show_event_time | 支付展示时间 |
| pay_suc_enter_method | 支付成功入口 |
| pay_suc_event_time | 支付成功时间 |
| pre_first_scenario | 支付前对话场景 |
| after_first_scenario | 支付后对话场景 |
| pre_kfc_user_agent | 支付前KFC用户代理 |
| after_kfc_user_agent | 支付后KFC用户代理 |
| pre_model_type | 支付前用户代理类型 |
| after_model_type | 支付后用户代理类型 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（订单归因概览）**
```sql
order_id AS `订单ID`,
user_id AS `用户ID`,
goods_id AS `商品ID`,
status AS `订单状态`,
pay_channel AS `支付渠道`,
platform AS `付费平台`,
action_type AS `操作类型`,
select_enter_method AS `套餐选择入口`,
pay_suc_enter_method AS `支付成功入口`,
actual_paid_price AS `实际支付金额`,
currency AS `币种`
```

**支付场景归因导出**
```sql
order_id AS `订单ID`,
user_id AS `用户ID`,
pre_chat_id AS `支付前聊天ID`,
pre_model AS `支付前模型`,
pre_first_scenario AS `支付前场景`,
after_chat_id AS `支付后聊天ID`,
after_model AS `支付后模型`,
after_first_scenario AS `支付后场景`,
pay_show_event_time AS `支付展示时间`,
pay_suc_event_time AS `支付成功时间`
```

**页面入口归因导出**
```sql
order_id AS `订单ID`,
user_id AS `用户ID`,
show_enter_method AS `套餐页展现入口`,
select_enter_method AS `套餐选择入口`,
pay_show_enter_method AS `支付页展现入口`,
pay_show_track_id AS `支付展示追踪ID`,
pay_suc_enter_method AS `支付成功入口`,
pay_suc_track_id AS `支付成功追踪ID`,
platform AS `付费平台`,
action_type AS `操作类型`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

**查询各支付成功入口的订单量和金额**
```sql
SELECT 
    pay_suc_enter_method AS `支付成功入口`,
    COUNT(*) AS `订单数`,
    SUM(actual_paid_price) AS `总支付金额`,
    AVG(actual_paid_price) AS `平均支付金额`
FROM dwm_pay_order_attribute_di
WHERE dt = '2026-03-12'
  AND status = 1
GROUP BY pay_suc_enter_method
ORDER BY COUNT(*) DESC
```

**查询支付前后的模型使用情况**
```sql
SELECT 
    pre_model AS `支付前模型`,
    after_model AS `支付后模型`,
    COUNT(*) AS `订单数`,
    SUM(actual_paid_price) AS `总支付金额`
FROM dwm_pay_order_attribute_di
WHERE dt = '2026-03-12'
  AND status = 1
GROUP BY pre_model, after_model
ORDER BY COUNT(*) DESC
```

**查询特定对话场景的转化订单**
```sql
SELECT 
    pre_first_scenario AS `支付前场景`,
    pay_suc_enter_method AS `支付成功入口`,
    COUNT(*) AS `订单数`,
    AVG(actual_paid_price) AS `平均支付金额`
FROM dwm_pay_order_attribute_di
WHERE dt = '2026-03-12'
  AND status = 1
  AND pre_first_scenario IS NOT NULL
GROUP BY pre_first_scenario, pay_suc_enter_method
ORDER BY COUNT(*) DESC
LIMIT 20
```

[待补充]
