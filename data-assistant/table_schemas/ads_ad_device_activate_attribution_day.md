# ads_ad_device_activate_attribution_day

## 别名
设备激活归因表, 设备归因表, 激活归因明细表

## 描述
设备激活归因明细表，记录每个设备的激活归因信息，包含设备信息、归因渠道、广告计划等，支持按 device_id 查询设备的完整归因链路。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 无主键
- 典型场景：设备级归因分析、激活来源追踪、广告效果评估

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | ads_ad_device_activate_attribution_day | - | - | ODPS 项目 mart_kimi |
| hologres | ads_ad_device_activate_attribution_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| activate_time_ms | 激活时间戳 |
| device_activation_row_num | 激活次数 |
| ssid_array | SSID列表 |
| user_id_array | 用户ID列表 |
| attribution_subtype | 归因指纹类型 |
| source_type | 激活来源类型 |
| tracer_unique_id | 广告跟踪ID |
| etat | 广告到激活间隔秒 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
device_id AS `设备ID`,
activate_time_ms AS `激活时间戳`,
is_new_device AS `是否新设备`,
os AS `操作系统`,
attribution_type AS `归因类型`,
source AS `激活渠道`
```

**归因详情导出**
```sql
dt AS `日期`,
device_id AS `设备ID`,
activate_time_ms AS `激活时间戳`,
device_activation_row_num AS `激活次数`,
ssid_array AS `SSID列表`,
user_id_array AS `用户ID列表`,
is_new_device AS `是否新设备`,
os AS `操作系统`,
attribution_type AS `归因类型`,
attribution_subtype AS `归因指纹类型`,
loc_country_id AS `国家ID`,
loc_province_id AS `省份ID`,
loc_city_id AS `城市ID`,
source_type AS `激活来源类型`,
source AS `激活渠道`
```

**广告计划导出**
```sql
dt AS `日期`,
device_id AS `设备ID`,
tracer_unique_id AS `广告跟踪ID`,
tracking_id AS `广告活动ID`,
account_id AS `广告账户ID`,
campaign_id AS `广告组ID`,
creative_id AS `广告创意ID`,
ad_id AS `广告计划ID`,
source AS `激活渠道`,
etat AS `广告到激活间隔秒`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
