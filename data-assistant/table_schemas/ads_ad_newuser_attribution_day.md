# ads_ad_newuser_attribution_day

## 别名
新用户归因表, 新增SSID归因表, 移动端新用户归因表

## 描述
新用户归因明细表，记录当日移动端新增 SSID 的归因信息，包含设备信息、首次访问地理位置、广告归因渠道等。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 无主键（每日新增用户快照）
- 数据范围：当日移动端新增的 SSID
- 典型场景：新用户来源分析、渠道质量评估、拉新效果监控

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | ads_ad_newuser_attribution_day | - | - | ODPS 项目 mart_kimi |
| hologres | ads_ad_newuser_attribution_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| device_type | 设备类型 |
| first_regist_user_id | 首次注册用户ID |
| first_visit_province | 首次访问省份 |
| first_visit_city | 首次访问城市 |
| first_visit_city_level | 首次访问城市线级 |
| source_type | 来源类型 |
| attribution_subtype | 归因指纹类型 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
ssid AS `SSID`,
device_id AS `设备ID`,
device_type AS `设备类型`,
first_regist_user_id AS `首次注册用户ID`,
os AS `操作系统`,
source AS `归因渠道`,
source_type AS `来源类型`
```

**归因详情导出**
```sql
dt AS `日期`,
ssid AS `SSID`,
device_id AS `设备ID`,
device_type AS `设备类型`,
first_regist_user_id AS `首次注册用户ID`,
user_id_array AS `用户ID列表`,
os AS `操作系统`,
first_visit_province AS `首次访问省份`,
first_visit_city AS `首次访问城市`,
first_visit_city_level AS `首次访问城市线级`,
source AS `归因渠道`,
source_type AS `来源类型`,
attribution_subtype AS `归因指纹类型`
```

**广告计划导出**
```sql
dt AS `日期`,
ssid AS `SSID`,
device_id AS `设备ID`,
source AS `归因渠道`,
source_type AS `来源类型`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

[待补充]
