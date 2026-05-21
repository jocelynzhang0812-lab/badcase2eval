# dws_finder_user_detail_day

## 别名
Finder用户宽表, SSID用户宽表, 访客用户表, 设备用户表

## 描述
Finder/火山 SSID 粒度用户宽表，记录访客级别（设备维度）的用户行为、归因、首访信息等。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 ssid（火山用户唯一标识符）
- **数据特性**：每天分区包含截止当前的历史全量 SSID（累积型快照表），而非仅当日新增
- 与 dws_kimi_user_detail_day 区分：本表是 SSID/设备粒度（访客级），AI_Platform 用户表是 user_id 粒度（注册用户级）
- 典型场景：分析访客留存、首访归因、设备级行为

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_finder_user_detail_day | - | - | ODPS 项目 mart_kimi |
| hologres | dws_finder_user_detail_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| first_regist_user_id | 首次注册用户ID |
| is_new_ssid | 是否新SSID |
| is_new_campaign_user | 是否广告拉新用户 |
| first_visit_ip | 首次访问IP |
| first_visit_province | 首次访问省份 |
| first_visit_city | 首次访问城市 |
| is_first_day_registered | 首日是否注册 |
| is_first_day_visit | 首日是否访问 |
| is_first_day_sent_message | 首日是否发消息 |
| first_pay_day | 首次付费日期 |
| first_pay_price | 首次付费金额 |
| visit_cnt | 访问次数 |
| send_msg_cnt | 发消息次数 |
| create_chat_cnt | 新建会话数 |
| last_visit_dt | 上次活跃日期 |
| latest_visit_dt | 最新活跃日期 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
ssid AS `SSID`,
user_id AS `用户ID`,
is_new_ssid AS `是否新SSID`,
is_new_campaign_user AS `是否广告拉新`,
first_visit_platform AS `首次平台`,
first_visit_province AS `首次省份`,
first_visit_city AS `首次城市`,
membership_level AS `会员等级`,
first_pay_day AS `首次付费日期`,
visit_cnt AS `访问次数`
```

**首次归因导出**
```sql
dt AS `日期`,
ssid AS `SSID`,
first_regist_user_id AS `首次注册用户ID`,
first_utm_source_vulcano AS `火山首次渠道`,
first_utm_campaign_vulcano AS `火山首次活动`,
attribution_type_vulcano AS `火山归因类型`,
first_utm_source_self AS `自建首次渠道`,
first_utm_campaign_self AS `自建首次活动`,
attribution_type_self AS `自建归因类型`,
account_id AS `广告账户ID`,
first_campaign_id_self AS `自建广告系列ID`,
first_adgroup_id_self AS `自建广告组ID`,
first_ad_id_self AS `自建广告ID`
```

**留存行为导出**
```sql
dt AS `日期`,
ssid AS `SSID`,
user_id AS `用户ID`,
is_first_day_registered AS `首日是否注册`,
is_first_day_visit AS `首日是否访问`,
is_first_day_sent_message AS `首日是否发消息`,
first_send_msg_time AS `首次发消息时间`,
last_send_msg_time AS `末次发消息时间`,
first_visit_dt AS `首次访问日期`,
last_visit_dt AS `上次活跃日期`,
latest_visit_dt AS `最新活跃日期`,
visit_cnt AS `访问次数`,
send_msg_cnt AS `发消息次数`,
create_chat_cnt AS `新建会话数`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
