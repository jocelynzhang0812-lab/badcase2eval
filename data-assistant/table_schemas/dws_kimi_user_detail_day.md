# dws_kimi_user_detail_day

## 别名
Kimi用户宽表, 注册用户宽表, 产品用户表, user_id用户表

## 描述
AI_Platform C端产品用户明细宽表（user_id 粒度），包含注册用户的基础信息、行为数据、会员订阅信息、各产品使用统计（Internal_Tool、深度研究、K2、PPT、Coding等）。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 user_id（注册用户唯一标识）
- 与 dws_finder_user_detail_day 区分：本表是 user_id 粒度（注册用户级），Finder 表是 SSID 粒度（访客/设备级）
- 与 dws_saas_account_detail_day 区分：本表是 AI_Platform C端产品用户，非开放平台（B端）组织数据
- 包含用户生命周期全量指标，支持用户行为分析和画像构建

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_kimi_user_detail_day | - | - | ODPS 项目 mart_kimi |
| hologres | dws_kimi_user_detail_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| region | 用户地区 |
| platform | 末次使用平台 |
| is_sub | 是否订阅会员 |
| is_use_Internal_Tool_day | 当天是否使用Internal_Tool |
| is_use_dr_day | 当天是否使用深度研究 |
| is_use_k2_day | 当天是否使用K2 |
| is_use_k2_thinking_day | 当天是否使用K2 Thinking |
| is_use_ppt_day | 当天是否使用PPT |
| is_use_kfc_day | 当天是否使用Coding, 当天是否使用KFC |
| is_kfc_new_user | 是否Coding新用户, 是否KFC新用户 |
| kfc_request_cnt | Coding请求数, KFC请求数 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**用户基础信息**
```sql
dt AS `日期`,
user_id AS `用户ID`,
CASE WHEN user_id LIKE 'anon%' THEN '匿名用户' ELSE '注册用户' END AS `用户类型`,
created_at AS `注册时间`,
status AS `账号状态`,
region AS `地区`,
user_country_code AS `国家代码`,
first_platform AS `首次平台`,
platform AS `末次平台`
```

**会员订阅信息**
```sql
membership_level AS `会员等级`,
membership_status AS `会员状态`,
is_sub AS `是否订阅`,
first_sub_time AS `首次订阅时间`,
last_end_time AS `订阅到期时间`,
first_goods_title AS `首次订阅商品`,
first_actual_price_in_cny AS `首次订阅金额`,
last_goods_title AS `最近订阅商品`,
last_actual_price_in_cny AS `最近订阅金额`
```

**产品使用统计**
```sql
is_use_Internal_Tool_day AS `使用Internal_Tool`,
is_use_dr_day AS `使用深度研究`,
is_use_k2_day AS `使用K2`,
is_use_k2_thinking_day AS `使用K2T`,
is_use_k2d5_day AS `使用K2.5`,
is_use_ppt_day AS `使用PPT`,
is_use_kfc_day AS `使用Coding`,
chat_cnt AS `会话数`,
segment_cnt AS `交互轮数`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
