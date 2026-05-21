# 工具使用示例

本文档提供 Internal_Tool Trajectory Debugger 工具的使用示例和最佳实践。

---

## 快速开始

### 1. 获取紧凑轨迹（文本格式）

适合快速查看对话流程和关键节点。

```python
from kimi_model import KimiInternalTools

chat_id = "19c419ab-5162-8e71-8000-09feaa043f18"
trajectory = KimiInternalTools.get_compact_trajectory(chat_id)

# 打印前 20 行
for line in trajectory[:20]:
    print(line)
```

**输出示例**:
```
[user_query][turn_1] 用户输入内容...
[model_resp][turn_1][step_1] 模型响应内容...
[tool_call] Tool Name: todo_read, Tool Call ID: mshtools-todo_read:0, Tool Args: {}
[model_usage] {"input_tokens": 1000, "output_tokens": 200}
```

---

### 2. 获取完整轨迹（JSON格式）

适合深度分析，包含完整的 blocks 元数据。

#### 命令行使用

```bash
# 获取前 10 条消息
python3 scripts/get_full_trajectory.py 19c419ab-5162-8e71-8000-09feaa043f18 --limit 10

# 保存到文件
python3 scripts/get_full_trajectory.py 19c419ab-5162-8e71-8000-09feaa043f18 --output trajectory.json

# 分页获取（从第 10 条开始）
python3 scripts/get_full_trajectory.py 19c419ab-5162-8e71-8000-09feaa043f18 --offset 10 --limit 20
```

#### Python 调用

```python
import sys
sys.path.insert(0, 'scripts')
from get_full_trajectory import get_full_trajectory

result = get_full_trajectory(
    chat_id="19c419ab-5162-8e71-8000-09feaa043f18",
    offset=0,
    limit=50
)

# 查看统计信息
print(f"总消息数: {result['summary']['total_messages']}")
print(f"Blocks统计: {result['summary']['statistics']}")

# 遍历消息
for msg in result['messages']:
    print(f"[{msg['role']}] {msg['block_count']} blocks")
    for block in msg['blocks']:
        if block['type'] == 'tool':
            print(f"  Tool: {block['tool_name']}")
```

---

### 3. 获取产出文件列表

```python
from kimi_model import KimiInternalTools

files = KimiInternalTools.get_Internal_Tool_files(chat_id)

if files:
    for f in files:
        print(f"{f['name']} ({f['size']} bytes) - {f['extension']}")
else:
    print("该 chat_id 没有产出文件")
```

---

## 常见分析场景

### 场景 1：检查工具调用错误

```python
result = get_full_trajectory(chat_id, limit=100)

error_count = 0
for msg in result['messages']:
    for block in msg.get('blocks', []):
        if block.get('has_error'):
            error_count += 1
            print(f" Error in {block.get('tool_name', 'unknown')}")
            print(f"   {block.get('error_preview', 'No details')}")

print(f"\n总计错误: {error_count}")
```

---

### 场景 2：统计文件输出

```python
result = get_full_trajectory(chat_id)
stats = result['summary']['statistics']

print(f" 文件输出数量: {len(stats['file_outputs'])}")
for f in stats['file_outputs']:
    print(f"  - {f['file_name']} ({f['file_type']})")
```

---

### 场景 3：分析 Token 使用情况

```python
from kimi_model import KimiInternalTools

trajectory = KimiInternalTools.get_compact_trajectory(chat_id)

# 提取所有 model_usage
import json
import re

total_input = 0
total_output = 0

for line in trajectory:
    if '[model_usage]' in line:
        match = re.search(r'\{.*\}', line)
        if match:
            usage = json.loads(match.group())
            total_input += usage.get('input_tokens', 0)
            total_output += usage.get('output_tokens', 0)

print(f"总输入 Tokens: {total_input}")
print(f"总输出 Tokens: {total_output}")
print(f"总计: {total_input + total_output}")
```

---

### 场景 4：查找特定工具调用

```python
result = get_full_trajectory(chat_id, limit=100)

target_tool = "write_file"
found_calls = []

for msg in result['messages']:
    for block in msg.get('blocks', []):
        if block.get('type') == 'tool' and target_tool in block.get('tool_name', ''):
            found_calls.append({
                'tool': block['tool_name'],
                'args': block.get('args_preview', '')
            })

print(f"找到 {len(found_calls)} 个 {target_tool} 调用:")
for call in found_calls:
    print(f"  - {call['tool']}: {call['args'][:100]}...")
```

---

### 场景 5：检查部署情况

```python
result = get_full_trajectory(chat_id)

deployment_info = None
for msg in result['messages']:
    for block in msg.get('blocks', []):
        if block.get('type') == 'tool' and 'deploy' in block.get('tool_name', ''):
            deployment_info = block
            break

if deployment_info:
    print(" 找到部署调用:")
    print(f"   工具: {deployment_info['tool_name']}")
    print(f"   参数: {deployment_info['args_preview']}")
else:
    print(" 未找到部署调用")
```

---

## 数据保存最佳实践

### 保存完整分析数据

```python
import json
import os

chat_id = "19c419ab-5162-8e71-8000-09feaa043f18"
debug_dir = f"/qa/qa/hualiang/qa_intern/agent_debug_log/debug_log/{chat_id}"
os.makedirs(debug_dir, exist_ok=True)

# 1. 保存紧凑轨迹
trajectory = KimiInternalTools.get_compact_trajectory(chat_id)
with open(f"{debug_dir}/trajectory_compact.txt", "w") as f:
    f.writelines(trajectory)

# 2. 保存完整轨迹
result = get_full_trajectory(chat_id)
with open(f"{debug_dir}/trajectory_full.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# 3. 保存文件列表
files = KimiInternalTools.get_Internal_Tool_files(chat_id)
with open(f"{debug_dir}/files.json", "w") as f:
    json.dump(files, f, ensure_ascii=False, indent=2)

print(f" 数据已保存到: {debug_dir}/")
```

---

## 故障排除

### 问题 1：ImportError: No module named 'kimi_model'

**解决**: 确保将 agent_debug_log 目录添加到 Python 路径

```python
import sys
sys.path.insert(0, '/qa/qa/hualiang/qa_intern/agent_debug_log')
from kimi_model import KimiInternalTools
```

### 问题 2：获取到的数据为空

**可能原因**:
- Chat ID 不正确
- 该 chat_id 不存在
- API 访问权限问题

**检查**:
```python
result = KimiInternalTools.get_chat_content(chat_id)
if result is None or result.empty:
    print("未找到数据，请检查 chat_id")
```

### 问题 3：SSL 警告

出现的 `NotOpenSSLWarning` 警告不影响功能，可以忽略。如需消除:

```bash
export PYTHONWARNINGS="ignore:NotOpenSSLWarning"
```

---

## 参考资料

- [SKILL.md](../SKILL.md) - 主文档（分析流程和标准）
- [Internal_Tool-trajectory-troubleshooting.md](Internal_Tool-trajectory-troubleshooting.md) - Internal_Tool 产出物问题排查

