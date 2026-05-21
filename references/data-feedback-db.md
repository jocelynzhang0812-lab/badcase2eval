---
name: data-feedback-db
description: 【通用】连接 regression 数据库检索用户反馈信息。支持 feedback_subscription（订阅用户反馈）、feedback_Internal_Tool（Agent/Internal_Tool反馈）等表，可查询用户反馈内容、订阅信息、点赞状态等。适用于 AI_Platform Agent 和 AI_Platform Claw 反馈分析。
---

# Feedback 数据库检索

**适用范围：通用（AI_Platform Agent + AI_Platform Claw）**

**全量用户反馈数据查询工具**。用于连接 regression 数据库查询用户反馈记录，支持灵活的 SQL 查询、统计分析和数据导出。

**核心用途**:
- 按 chat_id / user_id / thread_id 查询具体反馈
- 搜索统计某一类反馈（按关键词、时间、状态等）
- 任意操作 feedback_subscription 和 feedback_Internal_Tool 表的数据
- 灵活的自定义 SQL 查询和数据导出

## 数据库连接信息

- **Host**: mysql7e9f4ef1a927.rds.ivolces.com
- **Database**: regression
- **User**: superdba
- **Charset**: utf8mb4

---

## 表说明

### 1. feedback_subscription 表 ⭐ 订阅用户反馈
**用途**: 存储**订阅用户**的反馈信息，包含商业化订阅数据。

| 字段 | 说明 |
|------|------|
| feedback_id | 反馈ID |
| content | 反馈内容 |
| user_id | 用户ID |
| chat_id | 聊天ID |
| **thread_id** | **[Internal Docs Platform]卡片线程ID** ⭐ |
| subscription_type | 订阅类型（Moderato/Andante等）|
| subscription_status | 订阅状态（订阅中/未支付/已取消/订阅停止等）|
| subscription_region | 地区（CN/Overseas）|
| thumb_status | 点赞状态（0=无，1=赞，2=踩）|
| chat_model | 使用的模型 |
| problem_type | 问题类型 |
| skill_type | 技能类型 |

**适用场景**:
- 查询**付费/订阅用户**的反馈
- 分析订阅用户的满意度
- 关联[Internal Docs Platform]卡片线程

### 2. feedback_Internal_Tool 表 ⭐ Agent/OK Computer 反馈
**用途**: 存储**Agent/OK Computer**相关的反馈，包含JSON元数据和技能信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| feedback_id | varchar | 反馈ID |
| feedback_content | text | 反馈内容 |
| user_id | varchar | 用户ID |
| chat_id | varchar | 聊天ID |
| created_at | datetime | 创建时间 |
| feedback_type | varchar | 反馈类型 |
| **meta** | **json** | **元数据（来源、IP、模型等）** |
| **subscription_info** | **json** | **订阅信息（JSON格式）** |
| thumb_status | int | 点赞状态 |
| **user_query** | text | **用户原始查询内容** ⭐ |
| thread_id | varchar | [Internal Docs Platform]卡片线程ID |
| **skill_type** | varchar | **Skill类型** ⭐ |

**适用场景**:
- 查询**Agent/OK Computer**相关的反馈
- 分析特定技能的问题
- 查看用户原始查询和Agent行为
- 深度分析JSON元数据

### 表对比

| 对比项 | feedback_subscription | feedback_Internal_Tool |
|--------|----------------------|--------------|
| **主要用途** | 订阅用户反馈 | Agent/Internal_Tool 反馈 |
| **用户类型** | 付费/订阅用户 | 所有Agent用户 |
| **包含信息** | 订阅状态、商业化数据 | Skill类型、用户原始查询 |
| **JSON字段** | 较少 | meta、subscription_info |
| **典型查询** | 订阅用户满意度 | Agent行为分析 |

---

## 使用方法

### feedback_subscription 表查询（订阅用户）

```bash
# 按 chat_id 查询
python3 scripts/query_feedback.py --action sub_chat_id --value <chat_id>

# 按 thread_id 查询（[Internal Docs Platform]卡片线程）
python3 scripts/query_feedback.py --action sub_thread_id --value <thread_id>

# 按关键词搜索
python3 scripts/query_feedback.py --action sub_keyword --value "问题"

# 按点赞状态查询（0=无反馈，1=赞，2=踩）
python3 scripts/query_feedback.py --action sub_thumb --thumb 2

# 统计信息
python3 scripts/query_feedback.py --action sub_stats
```

### feedback_Internal_Tool 表查询（Agent/Internal_Tool反馈）

```bash
# 按 chat_id 查询
python3 scripts/query_feedback.py --action Internal_Tool_chat_id --value <chat_id>

# 按 thread_id 查询（[Internal Docs Platform]卡片线程）
python3 scripts/query_feedback.py --action Internal_Tool_thread_id --value <thread_id>

# 按关键词搜索
python3 scripts/query_feedback.py --action Internal_Tool_keyword --value "分析"

# 按点赞状态查询
python3 scripts/query_feedback.py --action Internal_Tool_thumb --thumb 2

# 统计信息
python3 scripts/query_feedback.py --action Internal_Tool_stats
```

### 联合查询

```bash
# 同时查询三个表，获取完整信息
python3 scripts/query_feedback.py --action combined --value <chat_id>

# 导出到文件
python3 scripts/query_feedback.py --action combined --value <chat_id> --output result.json
```

---

## 特殊字段说明

### JSON 字段解析

**feedback_Internal_Tool.meta 字段示例：**
```json
{
  "source": "web",
  "ip_location": "CN",
  "model": "AI_Platform-k2.5",
  "user_agent": "..."
}
```

**feedback_Internal_Tool.subscription_info 字段示例：**
```json
{
  "type": "Andante",
  "status": "active",
  "end_time": "2026-03-10 15:30:00"
}
```

### 订阅状态说明

| 状态值 | 说明 |
|--------|------|
| 订阅中 | 正常订阅状态 |
| 未支付 | 未完成的订阅 |
| 订阅取消(未到期) | 已取消但仍在有效期内 |
| 订阅停止 | 已过期或终止 |

---

## 常用查询场景

### 场景1：查询最新订阅用户反馈

```bash
# 查看最新10条订阅用户反馈
python3 scripts/query_feedback.py --action sub_stats

# 查看最新的差评
python3 scripts/query_feedback.py --action sub_thumb --thumb 2 --limit 20
```

### 场景2：分析特定 Agent Skill 的问题

```bash
# 查询特定 skill_type 的反馈
python3 -c "
import mysql.connector
cnx = mysql.connector.connect(
    user='superdba',
    password='<REGRESSION_DB_PASSWORD>',
    host='mysql7e9f4ef1a927.rds.ivolces.com',
    database='regression'
)
cursor = cnx.cursor(dictionary=True)
cursor.execute('SELECT * FROM feedback_Internal_Tool WHERE skill_type = %s ORDER BY created_at DESC LIMIT 10', ('ppt',))
for row in cursor.fetchall():
    print(row['feedback_content'])
cursor.close()
cnx.close()
"
```

### 场景3：关联[Internal Docs Platform]卡片分析

```bash
# 通过 thread_id 查询
python3 scripts/query_feedback.py --action sub_thread_id --value "oc_xxx"

# 同时查询 feedback_Internal_Tool 获取 Agent 详情
python3 scripts/query_feedback.py --action Internal_Tool_thread_id --value "oc_xxx"
```

### 场景4：灵活自定义 SQL 查询（带时间限制）

```bash
# 按 user_id 查询最近30天的反馈记录
python3 -c "
import mysql.connector
cnx = mysql.connector.connect(
    user='superdba',
    password='<REGRESSION_DB_PASSWORD>',
    host='mysql7e9f4ef1a927.rds.ivolces.com',
    database='regression'
)
cursor = cnx.cursor(dictionary=True)
cursor.execute('''
    SELECT feedback_content, thumb_status, created_at 
    FROM feedback_Internal_Tool 
    WHERE user_id = %s 
      AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    ORDER BY created_at DESC
''', ('USER_ID',))
for row in cursor.fetchall():
    print(f\"[{row['thumb_status']}] {row['created_at']}: {row['feedback_content'][:50]}...\")
cursor.close()
cnx.close()
"
```

### 场景5：统计特定时间范围内的反馈数量

```bash
# 统计最近7天内的差评数量
python3 -c "
import mysql.connector
cnx = mysql.connector.connect(
    user='superdba',
    password='<REGRESSION_DB_PASSWORD>',
    host='mysql7e9f4ef1a927.rds.ivolces.com',
    database='regression'
)
cursor = cnx.cursor()
cursor.execute('''
    SELECT COUNT(*) FROM feedback_Internal_Tool 
    WHERE thumb_status = 2 
      AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
''')
print(f\"最近7天差评数量: {cursor.fetchone()[0]}\")
cursor.close()
cnx.close()
"
```

### 场景6：查询 AI_Platform Claw 专属反馈 ⭐

**AI_Platform Claw 反馈特征**：
- 存储在 `feedback_subscription` 表
- `content` 字段包含 `【来自 AI_Platform Claw】` 标签
- 包含 `botId` 和 `botType` 的 JSON 元数据

```bash
# 查询今天的 AI_Platform Claw 反馈
python3 -c "
import mysql.connector
import json

cnx = mysql.connector.connect(
    user='superdba',
    password='<REGRESSION_DB_PASSWORD>',
    host='mysql7e9f4ef1a927.rds.ivolces.com',
    database='regression'
)
cursor = cnx.cursor(dictionary=True)

query = '''
SELECT 
    feedback_id,
    content,
    user_id,
    chat_id,
    thumb_status,
    subscription_status,
    subscription_type,
    created_at,
    thread_id,
    feedback_type,
    problem_type
FROM feedback_subscription 
WHERE DATE(created_at) = CURDATE()
  AND content LIKE '%【来自 AI_Platform Claw】%'
ORDER BY created_at DESC
LIMIT 50
'''

cursor.execute(query)
results = cursor.fetchall()

# 转换 bytes 和 datetime 为字符串
for r in results:
    for k, v in r.items():
        if isinstance(v, bytes):
            r[k] = v.decode('utf-8')
        elif hasattr(v, 'isoformat'):
            r[k] = v.isoformat()

print(json.dumps(results, indent=2, ensure_ascii=False))
cursor.close()
cnx.close()
"
```

**AI_Platform Claw vs Agent 反馈区别**：

| 类型 | 存储表 | 特征 | 查询条件 |
|------|--------|------|----------|
| **AI_Platform Claw** | feedback_subscription | content 包含 `【来自 AI_Platform Claw】` | `content LIKE '%【来自 AI_Platform Claw】%'` |
| **Agent/PPT** | feedback_subscription | content 包含 `【来自` 但不包含 `AI_Platform Claw` | `content LIKE '%【来自%' AND content NOT LIKE '%【来自 AI_Platform Claw】%'` |
| **OK Computer** | feedback_Internal_Tool | meta 字段包含 Agent 相关信息 | 查询 feedback_Internal_Tool 表 |

---

## 灵活查询指南

**feedback-db-retrieval 是一个通用的用户反馈数据库查询工具**，任何可以操作 `feedback_subscription` 和 `feedback_Internal_Tool` 表的操作都可以使用。

### 第一步：查看表 Schema

写查询前，先了解表结构和字段：

```bash
# 查看 feedback_Internal_Tool 表的字段
python3 -c "
import mysql.connector
cnx = mysql.connector.connect(
    user='superdba',
    password='<REGRESSION_DB_PASSWORD>',
    host='mysql7e9f4ef1a927.rds.ivolces.com',
    database='regression'
)
cursor = cnx.cursor()
cursor.execute('DESCRIBE feedback_Internal_Tool')
for row in cursor.fetchall():
    print(f'{row[0]:20} {row[1]:20} {row[2]}')
cursor.close()
cnx.close()
"

# 查看 feedback_subscription 表的字段
python3 -c "
import mysql.connector
cnx = mysql.connector.connect(...)
cursor = cnx.cursor()
cursor.execute('DESCRIBE feedback_subscription')
for row in cursor.fetchall():
    print(f'{row[0]:20} {row[1]:20} {row[2]}')
cursor.close()
cnx.close()
"
```

### 第二步：编写查询（️ 必须加时间限制）

**重要：避免全表扫描，默认必须加上时间范围限制！**

```python
import mysql.connector

cnx = mysql.connector.connect(
    user='superdba',
    password='<REGRESSION_DB_PASSWORD>',
    host='mysql7e9f4ef1a927.rds.ivolces.com',
    database='regression'
)
cursor = cnx.cursor(dictionary=True)

# === 查询模板（必须包含时间限制）===
cursor.execute("""
    SELECT * FROM feedback_Internal_Tool 
    WHERE created_at >= %s          -- 时间限制（必需）
      AND created_at < %s           -- 时间限制（必需）
      AND [其他条件]
    ORDER BY created_at DESC 
    LIMIT 100
""", ('2025-02-01 00:00:00', '2025-03-01 00:00:00'))
# ===================================

for row in cursor.fetchall():
    print(row)

cursor.close()
cnx.close()
```

### 常用查询条件参考

根据表字段灵活组合查询条件：

| 字段 | 用途 | 示例 |
|------|------|------|
| `user_id` | 查询特定用户 | `user_id = 'xxx'` |
| `chat_id` | 查询特定会话 | `chat_id = 'xxx'` |
| `thread_id` | 关联[Internal Docs Platform]卡片 | `thread_id = 'oc_xxx'` |
| `created_at` | 时间范围（**必需**） | `created_at >= '2025-02-01'` |
| `thumb_status` | 点赞状态 | `thumb_status = 2` (踩) |
| `feedback_content` | 内容搜索 | `feedback_content LIKE '%xxx%'` |
| `skill_type` | Agent 技能类型 | `skill_type = 'ppt'` |
| `subscription_type` | 订阅类型 | `subscription_type = 'Andante'` |

### SQL 查询示例（都带时间限制）

```sql
-- 1. 查询某用户最近30天的反馈
SELECT feedback_content, thumb_status, created_at 
FROM feedback_Internal_Tool 
WHERE user_id = 'xxx' 
  AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY created_at DESC;

-- 2. 统计某 skill 最近7天的点赞率
SELECT 
    skill_type,
    COUNT(*) as total,
    SUM(CASE WHEN thumb_status = 1 THEN 1 ELSE 0 END) as thumbs_up,
    SUM(CASE WHEN thumb_status = 2 THEN 1 ELSE 0 END) as thumbs_down
FROM feedback_Internal_Tool 
WHERE skill_type = 'ppt'
  AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY skill_type;

-- 3. 搜索包含特定关键词的反馈（最近90天）
SELECT * FROM feedback_subscription 
WHERE (content LIKE '%崩溃%' OR content LIKE '%error%')
  AND created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY);

-- 4. 查询特定时间段的反馈
SELECT * FROM feedback_Internal_Tool 
WHERE created_at >= '2025-02-01 00:00:00' 
  AND created_at < '2025-03-01 00:00:00';

-- 5. 关联两个表查询（最近30天）
SELECT 
    Internal_Tool.chat_id,
    Internal_Tool.feedback_content,
    sub.subscription_type,
    sub.subscription_status
FROM feedback_Internal_Tool Internal_Tool
LEFT JOIN feedback_subscription sub ON Internal_Tool.chat_id = sub.chat_id
WHERE Internal_Tool.user_id = 'xxx'
  AND Internal_Tool.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY);
```

---

## 依赖安装

```bash
pip3 install mysql-connector-python
```

