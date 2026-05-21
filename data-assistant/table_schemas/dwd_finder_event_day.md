# dwd_finder_event_day

## 别名
埋点日志表, 火山埋点事件表, finder事件表

## 描述
火山 Finder 埋点事件明细表，记录用户行为事件数据，包含事件信息、用户信息、设备信息、归因信息等。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 无主键
- 包含动态参数字段（string_params, int_params），支持灵活的事件属性扩展

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dwd_finder_event_day | - | - | ODPS 项目 mart_kimi |
| hologres | dwd_finder_event_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| event | 事件名称 |
| user_id | 用户ID |
| ssid | 设备SSID |
| device_id | 设备ID |
| chat_id | 会话ID |
| segment_id | 消息ID |
| platform | 平台 |
| utm_source | 推广渠道 |
| utm_campaign | 推广活动 |
| utm_medium | 推广渠道名称 |
| event_time | 事件时间 |
| server_time | 服务器时间 |

## 计算字段

| 字段名称 | 别名 | 表达式 |
|---------|------|--------|
| [待补充] | [待补充] | [待补充] |

## 常用字段组合

**核心字段（快速探查）**
```sql
dt AS `日期`,
event AS `事件名称`,
user_id AS `用户ID`,
platform AS `平台`,
event_time AS `事件时间`
```

**用户设备信息导出**
```sql
dt AS `日期`,
event AS `事件名称`,
user_id AS `用户ID`,
ssid AS `设备SSID`,
device_id AS `设备ID`,
web_id AS `WebID`,
user_agent AS `UA`,
client_ip AS `IP`,
os_name AS `操作系统`,
os_version AS `系统版本`,
device_brand AS `设备品牌`,
device_model AS `设备型号`,
region AS `地区`,
platform AS `平台`,
app_channel AS `App渠道`,
app_version AS `App版本`
```

**归因信息导出**
```sql
dt AS `日期`,
event AS `事件名称`,
user_id AS `用户ID`,
utm_source AS `推广渠道`,
utm_campaign AS `推广活动`,
utm_medium AS `推广渠道名称`,
activation_type AS `激活类型`,
activation_channel AS `激活渠道`,
install_type AS `安装类型`,
register_type AS `注册类型`,
referrer AS `来源页面`
```

**会话上下文导出**
```sql
dt AS `日期`,
event AS `事件名称`,
user_id AS `用户ID`,
chat_id AS `会话ID`,
segment_id AS `消息ID`,
kimiplus_id AS `KimiPlusID`,
message_type AS `消息类型`,
reply_type AS `回复类型`,
page_path AS `页面路径`,
title AS `页面标题`
```

## 查询示例（fewshot，帮助大模型理解复杂需求）

### Visual Edit 埋点查询

> **背景**：`msh_visual_edit_end` 是用户在 Vibe Coding 产出的网页上进行可视化编辑（标注、选择等）后触发的埋点事件。
>
> **关键字段**：
> - `segment_id`：对应 `dws_chat_group_detail_day` 的 `assistant_segment_id`（被编辑的模型回复）
> - `string_params['edit_type']`：编辑类型，常见值 `annotate`（标注）、`select`（选择）
> - ️ 同一个 `segment_id` 可能对应**多条** `msh_visual_edit_end` 事件（用户对同一轮回复做了多次 annotate/select 操作）。与其他表 JOIN 时**必须先按 `segment_id` 去重**（`ROW_NUMBER() OVER (PARTITION BY segment_id, dt ORDER BY event_time)`，取 `rn = 1`），否则会产生笛卡尔积
>
> ℹ️ 完整的 Visual Edit 数据查询示例（三表关联取编辑后下一轮数据）见 `dws_chat_group_detail_day.md` 的「Vibe Coding Visual Edit 数据查询」章节。

```sql
-- 查询某天的 visual edit 事件
SELECT segment_id, dt, string_params['edit_type'] as edit_type, event_time
FROM mart_kimi.dwd_finder_event_day
WHERE dt = '2026-01-28'
  AND event = 'msh_visual_edit_end'
LIMIT 100
```
