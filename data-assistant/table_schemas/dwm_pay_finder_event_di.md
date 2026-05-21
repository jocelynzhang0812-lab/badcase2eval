# dwm_pay_finder_event_di

## 别名
订阅埋点流量表, 支付事件表, 订阅事件表

## 描述
订阅/支付相关的埋点事件表，从 dwd_finder_event_day 清洗出来的订阅埋点数据，包含会员展示、选择、支付展示、支付成功等事件。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 无主键（事件流水表）
- 数据来源：`dwd_finder_event_day` 过滤 event IN ('msh_membership_show', 'msh_membership_select', 'msh_payment_show', 'msh_payment_success')
- 与 dwd_finder_event_day 区分：本表仅包含订阅/支付相关埋点事件
- 典型场景：订阅转化漏斗分析、支付流程分析、会员购买行为分析

**事件说明**：
- `msh_membership_show`: 会员套餐页面展现
- `msh_membership_select`: 会员套餐选择
- `msh_payment_show`: 订单支付页面展现
- `msh_payment_success`: 支付成功

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dwm_pay_finder_event_di | - | - | ODPS 项目 mart_kimi |
| hologres | dwm_pay_finder_event_di | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| hash_uid | HashUID |
| ssid | SSID |
| device_id | 设备ID |
| stat_standard_id | 标准ID |
| user_agent | UA |
| client_ip | 客户端IP |
| os_name | 操作系统 |
| device_model | 设备型号 |
| region | 地区 |
| loc_province_id | 省份ID |
| loc_city_id | 城市ID |
| chat_id | 会话ID |
| segment_id | 消息ID |
| app_channel | App渠道 |
| page_path | 页面路径 |
| server_time | 服务器时间 |
| plan_name | 套餐名称 |
| msh_track_id | 跟踪ID |
| msh_order_id | 订单ID |
| msh_user_id | 订单用户ID |
| show_enter_method | 会员展现方式 |
| select_enter_method | 套餐选择方式 |
| pay_show_enter_method | 支付展现方式 |
| pay_show_track_id | 支付跟踪ID |
| pay_show_event_time | 支付展示时间 |
| pay_suc_enter_method | 支付成功方式 |
| pay_suc_track_id | 支付成功跟踪ID |
| pay_suc_event_time | 支付成功时间 |
## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
event AS `事件名称`,
ssid AS `SSID`,
user_id AS `用户ID`,
platform AS `平台`,
event_time AS `事件时间`,
plan_name AS `套餐名称`,
enter_method AS `进入方式`,
msh_order_id AS `订单ID`
```

**支付漏斗导出**
```sql
dt AS `日期`,
event AS `事件名称`,
ssid AS `SSID`,
user_id AS `用户ID`,
platform AS `平台`,
app_version AS `App版本`,
utm_source AS `推广渠道`,
utm_campaign AS `推广活动`,
event_time AS `事件时间`,
plan_name AS `套餐名称`,
enter_method AS `进入方式`,
msh_track_id AS `跟踪ID`,
msh_order_id AS `订单ID`,
msh_user_id AS `订单用户ID`,
pay_show_enter_method AS `支付展现方式`,
pay_suc_enter_method AS `支付成功方式`,
pay_suc_event_time AS `支付成功时间`
```

**用户设备导出**
```sql
dt AS `日期`,
event AS `事件名称`,
ssid AS `SSID`,
user_id AS `用户ID`,
device_id AS `设备ID`,
os_name AS `操作系统`,
device_brand AS `设备品牌`,
device_model AS `设备型号`,
region AS `地区`,
loc_province_id AS `省份ID`,
loc_city_id AS `城市ID`,
client_ip AS `客户端IP`,
user_agent AS `UA`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
