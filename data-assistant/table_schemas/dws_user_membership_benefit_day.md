# dws_user_membership_benefit_day

## 别名
用户会员权益信息表, 会员权益表, 用户权益表

## 描述
用户会员权益信息表，记录用户订阅的权益详情，包含深度研究、Internal_Tool、PPT等各类权益的总数和余量信息。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 user_id（用户唯一标识）
- 与 dws_kimi_user_detail_day 区分：本表聚焦会员权益余量，user_detail 表聚焦用户行为和用量统计
- 典型场景：查询用户权益余量、会员状态监控、权益耗尽预警

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_user_membership_benefit_day | - | - | ODPS 项目 mart_kimi |
| hologres | dws_user_membership_benefit_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| abstract_user_region | 用户地区 |
| abstract_user_country_code | 用户国家代码 |
| is_new_subscriber | 是否新订阅 |
| last_subscription_status | 最后订阅状态 |
| membership_status | 会员状态 |
| deep_research_total_ct | 深度研究总数 |
| deep_research_left_ct | 深度研究剩余 |
| ok_computer_total_ct | Internal_Tool总数 |
| ok_computer_left_ct | Internal_Tool剩余 |
| banana_ppt_total_ct | 香蕉PPT总数 |
| banana_ppt_left_ct | 香蕉PPT剩余 |
| ppt_total_ct | PPT总数 |
| ppt_left_ct | PPT剩余 |
| first_sub_time | 首次订阅时间 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
user_id AS `用户ID`,
membership_status AS `会员状态`,
is_new_subscriber AS `是否新订阅`,
deep_research_left_ct AS `深度研究剩余`,
ok_computer_left_ct AS `Internal_Tool剩余`,
ppt_left_ct AS `PPT剩余`
```

**权益详情导出**
```sql
dt AS `日期`,
user_id AS `用户ID`,
abstract_user_region AS `用户地区`,
abstract_user_country_code AS `用户国家代码`,
is_new_subscriber AS `是否新订阅`,
last_subscription_status AS `最后订阅状态`,
membership_status AS `会员状态`,
first_sub_time AS `首次订阅时间`
```

**权益余量导出**
```sql
dt AS `日期`,
user_id AS `用户ID`,
deep_research_total_ct AS `深度研究总数`,
deep_research_left_ct AS `深度研究剩余`,
ok_computer_total_ct AS `Internal_Tool总数`,
ok_computer_left_ct AS `Internal_Tool剩余`,
banana_ppt_total_ct AS `香蕉PPT总数`,
banana_ppt_left_ct AS `香蕉PPT剩余`,
ppt_total_ct AS `PPT总数`,
ppt_left_ct AS `PPT剩余`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

**查询权益即将耗尽的用户**
```sql
SELECT 
    user_id AS `用户ID`,
    membership_status AS `会员状态`,
    deep_research_left_ct AS `深度研究剩余`,
    ok_computer_left_ct AS `Internal_Tool剩余`,
    ppt_left_ct AS `PPT剩余`
FROM dws_user_membership_benefit_day
WHERE dt = '2026-03-12'
  AND (deep_research_left_ct <= 3 
       OR ok_computer_left_ct <= 3 
       OR ppt_left_ct <= 3)
```

**查询会员状态分布**
```sql
SELECT 
    membership_status AS `会员状态`,
    last_subscription_status AS `订阅状态`,
    COUNT(*) AS `用户数`
FROM dws_user_membership_benefit_day
WHERE dt = '2026-03-12'
GROUP BY membership_status, last_subscription_status
ORDER BY COUNT(*) DESC
```

**查询新订阅用户权益**
```sql
SELECT 
    user_id AS `用户ID`,
    first_sub_time AS `首次订阅时间`,
    deep_research_total_ct AS `深度研究总数`,
    deep_research_left_ct AS `深度研究剩余`,
    ok_computer_total_ct AS `Internal_Tool总数`,
    ok_computer_left_ct AS `Internal_Tool剩余`
FROM dws_user_membership_benefit_day
WHERE dt = '2026-03-12'
  AND is_new_subscriber = '1'
```

[待补充]
