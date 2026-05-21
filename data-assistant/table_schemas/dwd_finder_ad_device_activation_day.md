# dwd_finder_ad_device_activation_day

## 别名
设备激活表, 激活设备表, Finder设备激活表

## 描述
Finder广告设备激活表，记录每日从Finder广告事件表(finder_ad_event_day)中激活的设备信息，device_id粒度，包含设备基本信息、安装信息、激活时间和关联的SSID/用户ID列表。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 主键为 device_id（Finder设备唯一标识）
- 与 dws_finder_user_detail_day 区分：本表聚焦广告设备激活，dws_finder_user_detail_day 是访客明细表
- 典型场景：设备激活分析、广告转化归因、新设备追踪、设备安装来源分析

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dwd_finder_ad_device_activation_day | - | - | ODPS 项目 mart_kimi |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| ssid_array | SSID列表 |
| user_id_array | 用户ID列表 |
| device_activation_row_num | 设备激活序号 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（设备激活概览）**
```sql
dt AS `日期`,
device_id AS `设备ID`,
ssid_array AS `SSID列表`,
user_id_array AS `用户ID列表`,
activate_time AS `激活时间`,
is_new_device AS `是否新设备`,
package AS `安装包`,
app_version AS `App版本`,
os AS `操作系统`,
brand AS `设备品牌`,
model AS `设备型号`
```

**设备位置信息导出**
```sql
dt AS `日期`,
device_id AS `设备ID`,
loc_country_id AS `国家ID`,
loc_province_id AS `省份ID`,
loc_city_id AS `城市ID`,
activate_time AS `激活时间`,
is_new_device AS `是否新设备`,
tz_name AS `时区`
```

**设备标识信息导出**
```sql
dt AS `日期`,
device_id AS `设备ID`,
imei AS `IMEI`,
idfa AS `IDFA`,
android_id AS `AndroidID`,
oaid AS `OAID`,
caid1 AS `CAID1`,
caid2 AS `CAID2`,
activate_time AS `激活时间`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

**查询每日新设备激活量**
```sql
SELECT 
    dt AS `日期`,
    COUNT(*) AS `激活设备数`,
    COUNT(DISTINCT CASE WHEN is_new_device THEN device_id END) AS `新设备数`,
    ROUND(COUNT(DISTINCT CASE WHEN is_new_device THEN device_id END) * 100.0 / COUNT(*), 2) AS `新设备占比%`
FROM dwd_finder_ad_device_activation_day
WHERE dt BETWEEN '2026-03-01' AND '2026-03-12'
GROUP BY dt
ORDER BY dt DESC
```

**查询各品牌的设备激活分布**
```sql
SELECT 
    brand AS `设备品牌`,
    os AS `操作系统`,
    COUNT(*) AS `激活设备数`,
    COUNT(DISTINCT CASE WHEN is_new_device THEN device_id END) AS `新设备数`
FROM dwd_finder_ad_device_activation_day
WHERE dt = '2026-03-12'
GROUP BY brand, os
ORDER BY COUNT(*) DESC
LIMIT 20
```

**查询包含特定SSID的设备激活记录**
```sql
SELECT 
    device_id AS `设备ID`,
    activate_time AS `激活时间`,
    brand AS `品牌`,
    model AS `型号`,
    ssid_array AS `SSID列表`
FROM dwd_finder_ad_device_activation_day
WHERE dt = '2026-03-12'
  AND ARRAY_CONTAINS(ssid_array, 'specific_ssid_value')
ORDER BY activate_time DESC
LIMIT 100
```

[待补充]
