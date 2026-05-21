---
name: data-volc-event-logs
description: 【通用】查询火山引擎埋点系统(IFRINDER)事件日志数据，支持按用户ID、时间范围、会话ID查询用户行为事件。用于分析用户行为轨迹、排查问题、追踪异常事件。适用于 AI_Platform Agent 和 AI_Platform Claw 反馈分析。
---

# 火山埋点事件日志查询

**适用范围：通用（AI_Platform Agent + AI_Platform Claw）**

**用户行为分析的第一步**  查询用户在 AI_Platform 界面上的操作埋点信息（点击、发送、生成、导出等）。

这是 **初步分析工具**，用于：
- 了解用户在反馈时间点附近做了什么操作
- 发现异常事件（失败、加载错误等）
- 找到对应的 `chat_id` 或 `conversation_id`
- 定位问题发生的大致环节

**分析流程：**
```
volc-event-log-query (埋点分析) 
        ↓
   发现 chat_id / 异常事件
        ↓
agent-trajectory-debugger (深入分析 Agent 行为)
        ↓
   定位具体问题原因
```

**典型场景：**
- 用户反馈没有 chat_id（thumb_status=0）→ 用埋点找到对应会话
- 用户说"PPT生成失败" → 先查埋点看是否有 `msh_nppt_chat_failed` 事件
- 需要了解用户在反馈前的完整操作链路

## API 配置

- **查询 URL**: `http://172.24.128.60:8186/api/v1/feedback/events/query`
- **Grafana Trace**: `https://internal.company.com/explore`

## 支持的埋点事件

### 核心事件
| 事件名 | 说明 |
|--------|------|
| `msh_enter_chat_detail` | 进入聊天详情页 |
| `msh_sent_message` | 发送消息 |
| `msh_feedback_submit` | 提交反馈 |
| `msh_dislike` | 点踩 |

### PPT 相关事件
| 事件名 | 说明 |
|--------|------|
| `msh_nppt_chat_start` | PPT 对话开始 |
| `msh_nppt_chat_failed` | PPT 对话失败 ⭐异常 |
| `msh_nppt_save_start` | PPT 保存开始 |
| `msh_nppt_frame_load_start` | PPT 框架加载开始 |
| `msh_nppt_frame_load_end` | PPT 框架加载结束 |
| `msh_nppt_frame_show_end` | PPT 框架展示结束 |
| `msh_nppt_agentic_card_show` | Agentic 卡片展示 |
| `msh_nppt_agentic_card_click` | Agentic 卡片点击 |
| `msh_nppt_agentic_generate_end` | Agentic 生成结束 |
| `msh_nppt_generate_click` | 生成按钮点击 |
| `msh_nppt_generate_close` | 生成关闭 |
| `msh_nppt_generate_end` | 生成结束 |
| `msh_nppt_export_start` | 导出开始 |
| `msh_nppt_export_end` | 导出结束 |
| `msh_nppt_html_badcase` | PPT HTML 异常 ⭐异常 |
| `msh_nppt_retry_dialog_click` | 重试对话框点击 |

### 工具/文件事件
| 事件名 | 说明 |
|--------|------|
| `msh_upload_file` | 上传文件 |
| `msh_upload_file_finish` | 上传文件完成 |
| `msh_tool_click` | 工具点击 |
| `msh_file_artifacts_show` | 文件产物展示 |
| `msh_file_artifacts_click` | 文件产物点击 |
| `msh_file_reader_download` | 文件产物页下载 |
| `sandbox_file_response_url_click` | 沙箱文件响应点击 |
| `msh_bot_click` | Bot 点击 |

### UI/侧边栏事件
| 事件名 | 说明 |
|--------|------|
| `msh_sidebar_show` | 侧边栏展开 |
| `msh_sidebar_close` | 侧边栏关闭 |

### 网络/系统事件
| 事件名 | 说明 |
|--------|------|
| `android_tech_net_status_count` | Android 网络状态 |
| `ios_dev_network_request_begin` | iOS 网络请求开始 |
| `ios_dev_network_request_failed` | iOS 网络请求失败 |
| `ios_dev_network_request_success` | iOS 网络请求成功 |
| `ios_dev_stream_start` | iOS 流开始 |
| `ios_dev_stream_failed` | iOS 流失败 |
| `msh_interrupt_reply` | 中断回复 ⭐异常 |
| `msh_payment_success` | 支付成功 |

### 异常事件列表
```python
EXCEPTION_EVENTS = [
    "msh_nppt_html_badcase",    # PPT HTML 异常
    "msh_nppt_chat_failed",     # PPT 对话失败
    "msh_interrupt_reply",      # 中断回复
]
```

## 使用方法

### 1. 按用户ID和反馈时间查询

```bash
# 基本查询
python3 scripts/data-query_buried_point.py \
    --action user_time \
    --user-id "crsal859roqpdqvl7mcg" \
    --feedback-time "2026-01-30 15:07:33" \
    --time-range 1

# 扩大时间范围到6小时
python3 scripts/data-query_buried_point.py \
    --action user_time \
    --user-id "xxx" \
    --feedback-time "2026-01-30 15:07:33" \
    --time-range 6 \
    --page-size 500

# 导出到文件
python3 scripts/data-query_buried_point.py \
    --action user_time \
    --user-id "xxx" \
    --feedback-time "2026-01-30 15:07:33" \
    --output result.json
```

### 2. 按会话ID查询

```bash
python3 scripts/data-query_buried_point.py \
    --action conversation \
    --conversation-id "19c0da07-4172-89e2-8000-0902cca1c60e" \
    --user-id "xxx" \
    --time-range 6
```

## 返回结果说明

```json
{
  "user_id": "用户ID",
  "feedback_time": "反馈时间",
  "query_range": {
    "start_time": "查询开始时间",
    "end_time": "查询结束时间"
  },
  "total_events": 100,
  "event_counts": {
    "msh_sent_message": 50,
    "msh_nppt_chat_start": 10
  },
  "conversation_ids": ["会话ID1", "会话ID2"],
  "platforms": {
    "web": 80,
    "ios": 20
  },
  "exception_events": [
    {
      "event": "msh_nppt_chat_failed",
      "time": "2026-01-30 15:07:33",
      "conversation_id": "xxx",
      "error_reason": "错误原因"
    }
  ],
  "events": [
    {
      "event": "事件名",
      "time": "北京时间",
      "server_time": "服务器时间",
      "conversation_id": "会话ID",
      "message_id": "消息ID",
      "message_type": "消息类型",
      "platform": "平台",
      "app_version": "App版本",
      "raw_params": {原始参数}
    }
  ],
  "grafana_urls": {
    "会话ID1": "https://internal.company.com/explore?..."
  }
}
```

## 常用场景

### 场景1：用户反馈无 chat_id（初步分析 → 深入分析）

当 `thumb_status = 0` 时，用户没有针对具体聊天点赞/点踩，需要先用埋点找到对应的会话。

```bash
# 步骤1：用 feedback-db-retrieval 获取 user_id 和 feedback_time

# 步骤2：查询反馈时间前后的埋点（初步分析）
python3 scripts/data-query_buried_point.py \
    --action user_time \
    --user-id "xxx" \
    --feedback-time "2026-02-10 15:30:00" \
    --time-range 2 \
    --output step1_buried.json

# 步骤3：从结果中提取 conversation_ids
jq '.conversation_ids' step1_buried.json

# 步骤4：用 agent-trajectory-debugger 深入分析 chat_id
# python3 skills/agent-trajectory-debugger/scripts/analyze_trajectory.py --chat-id "xxx"
```

**分析工作流程：**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Step 1: 用户反馈（无 chat_id / thumb_status=0）                      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Step 2: volc-event-log-query（初步分析）                            │
│  - 查询 feedback_time 前后的用户操作埋点                              │
│  - 发现用户的具体操作序列（点击、发送、生成等）                        │
│  - 识别异常事件（msh_nppt_chat_failed 等）                           │
│  - 获取对应的 conversation_id / chat_id                              │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  Step 3: agent-trajectory-debugger（深入分析）                       │
│  - 拉取完整的 Agent trajectory                                       │
│  - 分析每轮模型的输入、输出、工具调用                                  │
│  - 定位问题发生的具体环节                                             │
│  - 生成详细的评估报告                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

**️ 关键：时间线对齐**

埋点数据和 Agent trajectory 必须在**同一时间线**下对比观察：

```
时间线对齐示例：
─────────────────────────────────────────────────────────▶

[埋点] 14:20:00  msh_sent_message      用户发送消息
       14:20:02  msh_nppt_chat_start   PPT对话开始 
                ↓
[Trajectory]    [user_query][turn_1]   模型收到消息
                [tool_call] slides_generator
       14:20:10  [tool_result] Error: 服务异常
                ↓
[埋点] 14:20:30  msh_nppt_chat_failed  埋点记录失败 ️

通过时间对齐：
- 埋点的 msh_nppt_chat_failed (14:20:30) 对应 trajectory 的工具调用失败 (14:20:10)
- 确认问题发生在 slides_generator 调用环节
```

### 场景2：排查用户反馈的具体问题（定位问题环节）

用户反馈"生成失败"/"没反应"/"报错"，先查埋点定位问题环节。

```bash
# 查询用户反馈前后的埋点
python3 scripts/data-query_buried_point.py \
    --action user_time \
    --user-id "用户ID" \
    --feedback-time "2026-02-10 15:30:00" \
    --time-range 2 \
    --output feedback_analysis.json

# 分析要点：
# 1. 查看 exception_events 是否有异常事件
# 2. 查看 event_counts 了解用户操作序列
# 3. 从 grafana_urls 获取 Trace 链接查看详细链路
# 4. 找到 chat_id 后，用 agent-trajectory-debugger 深入分析 Agent 行为
```

### 场景3：分析 PPT 生成失败（异常事件排查）

```bash
# 查询 PPT 相关埋点
python3 scripts/data-query_buried_point.py \
    --action user_time \
    --user-id "xxx" \
    --feedback-time "2026-02-10 15:30:00" \
    --time-range 1 | \
    jq '.exception_events | map(select(.event | contains("nppt")))'
```

### 场景4：追踪特定会话的完整操作链路

```bash
# 查询特定会话的所有埋点
python3 scripts/data-query_buried_point.py \
    --action conversation \
    --conversation-id "19c0da07-4172-89e2-8000-0902cca1c60e" \
    --time-range 6
```

## 字段提取说明

从埋点 `params` 字段中提取的关键字段：

| 字段 | 说明 |
|------|------|
| `conversation_id` | 会话ID (msh_conversation_id) |
| `message_id` | 消息ID (msh_message_id) |
| `message_type` | 消息类型 |
| `input_mode` | 输入模式 |
| `enter_from` | 进入来源 |
| `platform` | 平台 (web/ios/android) |
| `app_version` | App 版本 |
| `bot_name` | Bot 名称 |
| `req_scenario` | 请求场景 |
| `slide_id` | PPT slide ID |
| `browser` | 浏览器 |
| `browser_version` | 浏览器版本 |
| `badcase_info` | 异常信息 |
| `is_success` | 是否成功 |
| `error_reason` | 错误原因 |

## 时间格式

支持的时间格式（均为北京时间 UTC+8）：
- `2026-01-30 15:07:33`
- `2026-01-30T15:07:33`
- `2026/01/30 15:07:33`
- `2026-01-30 15:07`
- `2026-01-30`

## 依赖安装

```bash
pip3 install requests
```

