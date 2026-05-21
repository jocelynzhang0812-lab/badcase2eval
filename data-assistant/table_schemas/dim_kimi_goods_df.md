# dim_kimi_goods_df

## 别名
订阅商品维表, 商品信息表, 会员商品表

## 描述
订阅商品信息全量表，记录所有订阅商品的完整信息，包括商品标题、价格、会员类型、有效期、状态、使用区域限制等。用于查询商品详情、价格计算、商品筛选等场景。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 goods_id（商品唯一标识）
- 与 dwd_pay_order_day 关联：通过 goods_id 关联订单商品信息
- 典型场景：商品信息查询、价格对比、商品状态筛选、会员类型分析

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dim_kimi_goods_df | - | - | ODPS 项目 mart_kimi |
| hologres | dim_kimi_goods_df | default | ext_mc_holo | Hologres 加速表 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| duration_days | 有效天数 |
| use_region | 使用地区 |
| prices | 多币种价格 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（商品基本信息）**
```sql
dt AS `日期`,
goods_id AS `商品ID`,
title AS `商品标题`,
sub_title AS `副标题`,
membership_type AS `会员类型`,
actual_price AS `实际价格元`,
currency AS `币种`,
status AS `商品状态`,
use_region AS `使用地区`
```

**商品有效期导出**
```sql
dt AS `日期`,
goods_id AS `商品ID`,
title AS `商品标题`,
duration AS `会员时长`,
duration_unit AS `时长单位`,
duration_days AS `有效天数`,
membership_type AS `会员类型`
```

**商品价格详情导出**
```sql
dt AS `日期`,
goods_id AS `商品ID`,
title AS `商品标题`,
actual_price AS `实际价格元`,
price_in_cents AS `价格分`,
currency AS `币种`,
prices AS `多币种价格JSON`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

**查询所有上架商品**
```sql
SELECT 
    goods_id AS `商品ID`,
    title AS `商品标题`,
    actual_price AS `实际价格元`,
    currency AS `币种`,
    membership_type AS `会员类型`,
    duration_days AS `有效天数`,
    use_region AS `使用地区`
FROM dim_kimi_goods_df
WHERE dt = '2026-03-12'
  AND status = 1
ORDER BY membership_type, actual_price
```

**查询各会员类型的商品数量和价格范围**
```sql
SELECT 
    membership_type AS `会员类型`,
    COUNT(*) AS `商品数量`,
    MIN(actual_price) AS `最低价格`,
    MAX(actual_price) AS `最高价格`,
    AVG(actual_price) AS `平均价格`
FROM dim_kimi_goods_df
WHERE dt = '2026-03-12'
  AND status = 1
GROUP BY membership_type
ORDER BY membership_type
```

**查询特定地区的可用商品**
```sql
SELECT 
    goods_id AS `商品ID`,
    title AS `商品标题`,
    title_en AS `英文标题`,
    actual_price AS `实际价格元`,
    currency AS `币种`,
    duration_days AS `有效天数`
FROM dim_kimi_goods_df
WHERE dt = '2026-03-12'
  AND status = 1
  AND visible = 1
  AND use_region = 1
ORDER BY actual_price
```

[待补充]
