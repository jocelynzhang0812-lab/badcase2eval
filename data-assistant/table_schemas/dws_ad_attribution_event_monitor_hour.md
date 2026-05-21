# dws_ad_attribution_event_monitor_hour

## 别名
广告归因时间表, 广告监控小时表, 归因事件小时表

## 描述
广告归因事件监控小时表，记录广告归因相关的事件数据，支持小时级监控分析。

- 离线表，数据小时级产出（每小时更新一次）
- 双分区：dt（日期，格式：yyyy-MM-dd）+ ht（小时，格式：HH）
- 无主键（事件流水表）
- 查询时必须同时指定 dt 和 ht 分区，或仅指定 dt（查询全天）
- 典型场景：小时级广告归因监控、实时性要求较高的归因分析

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_ad_attribution_event_monitor_hour | - | - | ODPS 项目 mart_kimi |
| hologres | dws_ad_attribution_event_monitor_hour | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

仅列出有别名字段（其他字段使用 ODPS comment）：

| 字段名称 | 别名 |
|---------|------|
| event_time | 事件时间 |
| event | 事件名称 |
| source | 渠道 |
| device_id | 设备ID |
| ssid | SSID |
| platform | 平台 |
| attribution_type | 归因类型 |
| os | 操作系统 |
| referer | 来源页 |
| referer_host | 来源域名 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
ht AS `小时`,
event_time AS `事件时间`,
event AS `事件名称`,
source AS `渠道`,
ssid AS `SSID`,
platform AS `平台`,
attribution_type AS `归因类型`
```

**归因分析导出**
```sql
dt AS `日期`,
ht AS `小时`,
event_time AS `事件时间`,
event AS `事件名称`,
source AS `渠道`,
attribution_type AS `归因类型`,
platform AS `平台`,
os AS `操作系统`,
device_id AS `设备ID`,
ssid AS `SSID`,
referer_host AS `来源域名`,
referer AS `来源页`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
