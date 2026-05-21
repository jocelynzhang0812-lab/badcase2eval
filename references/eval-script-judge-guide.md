# Script Judge 开发指南

从零写一个 Script Judge 脚本，到上传 Platform 跑通。含踩坑经验和完整参考实现。

---

## 快速开始

### 1. 写脚本

脚本必须是一个 Python 文件，用 `orbit_judge` 提供的 `AbstractScriptJudge` 基类：

```python
#!/usr/bin/env python
from orbit_judge import AbstractScriptJudge, JudgeContext, run_abstract_judge

class MyJudge(AbstractScriptJudge):
    def evaluate(self, context: JudgeContext) -> list[dict]:
        # context.data  → {"input": ..., "expected_output": ..., "metadata": ...}
        # context.traces → 路径: source/baseline 的 trajectory 和 workspace
        # context.runtime → {"source_batch_created_at": "..."}
        return [
            {"name": "my_score", "value": 0.8, "comment": "理由", "data_type": "NUMERIC"}
        ]

if __name__ == "__main__":
    run_abstract_judge(MyJudge())
```

> **也支持直接写 `main()` 模式**（读环境变量 + 写 `/workspace/scores.json`），但推荐用 `AbstractScriptJudge`，结构更清晰。

### 2. 写 pyproject.toml

```toml
[project]
name = "my-judge"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

> 不需要声明 `orbit_judge` 依赖它由 runner 容器内置提供。

### 3. 写 uv.lock

```toml
version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "my-judge"
version = "1.0.0"
source = { editable = "." }
```

> ️ **必须用 `source = { editable = "." }`**，不是 `{ virtual = "." }`。后者会导致 `uv sync --locked` 报错 "lockfile needs to be updated"。

### 4. 上传到 Platform

```bash
# 用 curl（目前无 CLI 命令）
curl -X POST "https://platform.internal.ai.com/api/script-configs" \
  -H "X-AuthGateway-Access-Token: $AuthGateway_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_judge.py",
    "description": "My custom judge",
    "pyprojectToml": "...",
    "uvLock": "...",
    "script": "..."
  }'
```

### 5. 跑 judge

```bash
node Platform.mjs judge \
  --judge-pattern script \
  --script-config my_judge.py \
  --source-batch <batchId> \
  [--baseline-batch <batchId>] \
  --dry-run
```

---

## 运行时环境

### 环境变量

脚本运行时自动注入的环境变量：

| 环境变量 | 内容 | 示例 |
|----------|------|------|
| `ORBIT_JUDGE_INPUT` | Dataset item input (JSON) | `{"query": "..."}` |
| `ORBIT_JUDGE_EXPECTED_OUTPUT` | 期望输出 (JSON) | `null` |
| `ORBIT_JUDGE_DATA_METADATA` | Item metadata (JSON) | `{"category": "..."}` |
| `ORBIT_JUDGE_SOURCE_TRACE_ID` | 被评 trace ID | `7696ace661ec...` |
| `ORBIT_JUDGE_BASELINE_TRACE_ID` | 对比 trace ID（GSB 时） | `0bb662f798d9...` |
| `ORBIT_JUDGE_COMPARISON_MODE` | 是否对比模式 | `"true"` |
| `ORBIT_JUDGE_SOURCE_BATCH_ID` | Source batch ID | `73736` |
| `ORBIT_JUDGE_SOURCE_BATCH_CREATED_AT` | Source batch 创建时间 | `2026-04-15T12:10:13.000Z` |
| `JUDGE_WORKSPACE` / `ORBIT_JUDGE_WORKSPACE_DIR` | 工作目录 | `/workspace` |

### 文件系统 (`/workspace/`)

| 路径 | 内容 |
|------|------|
| `source/trajectory.jsonl` | Source trace 的 chat 历史 |
| `source/workspace/` | Source trace 的工作空间文件 |
| `baseline/trajectory.jsonl` | Baseline trace 的 chat 历史（GSB 时） |
| `baseline/workspace/` | Baseline trace 的工作空间 |
| `scores.json` | **脚本输出**：评分结果 |

### 内置库

Runner 容器预装了 `orbit_judge` 包，提供：

```python
# 基类和上下文
from orbit_judge import AbstractScriptJudge, JudgeContext, run_abstract_judge
from orbit_judge.script_api import build_judge_context

# Langfuse 客户端（已配好凭证）
from orbit_judge._client import require_langfuse_client
from orbit_judge._traces import fetch_trace, restore_trace_artifacts
```

---

##  已知坑点

### 坑 1: trajectory.jsonl 被 response_only 过滤

**问题**：Script judge 的 `JUDGE__MODE` 固定为 `response_only`，不管你传不传 `judgeMode`。这意味着 `/workspace/source/trajectory.jsonl` 只包含最后一轮 user + 最后一个 assistant 消息，**所有中间的 tool_calls 都被删掉了**。

**原因**：Platform server 的 `buildScriptJudgeBatchConfig`（`judges.ts:105-110`）不传 `judgeMode` 给 `buildSharedJudgeBatchConfig`，默认 `response_only`。

**影响**：如果你的脚本需要分析 tool_calls（搜索词、工具调用参数等），从 `trajectory.jsonl` 读到的永远是空的。

**解决方案**：**直接从 Langfuse API 获取原始 trace**，绕过过滤。

```python
from orbit_judge._traces import fetch_trace

def get_tool_calls(trace_id: str) -> list[dict]:
    """从 Langfuse observations 中提取 tool calls（绕过 response_only 过滤）。"""
    trace = fetch_trace(trace_id)
    observations = getattr(trace, "observations", []) or []
    
    tool_calls = []
    for obs in observations:
        obs_type = getattr(obs, "type", "")
        
        # 方法 1: TOOL observations（推荐，最直接）
        if obs_type == "TOOL":
            inp = getattr(obs, "input", None)
            if isinstance(inp, dict):
                tool_calls.append(inp)
        
        # 方法 2: GENERATION output 中的 tool_calls
        if obs_type == "GENERATION":
            out = getattr(obs, "output", None)
            if isinstance(out, dict) and out.get("tool_calls"):
                tool_calls.extend(out["tool_calls"])
    
    return tool_calls
```

环境变量中有 trace ID：

```python
source_trace_id = os.getenv("ORBIT_JUDGE_SOURCE_TRACE_ID", "")
baseline_trace_id = os.getenv("ORBIT_JUDGE_BASELINE_TRACE_ID", "")
```

### 坑 2: uv.lock 格式

**问题**：`source = { virtual = "." }` 导致 `uv sync --locked` 报错 "lockfile needs to be updated"。

**解决方案**：**必须用 `source = { editable = "." }`**。

```toml
#  错误
[[package]]
name = "my-judge"
version = "1.0.0"
source = { virtual = "." }

#  正确
[[package]]
name = "my-judge"
version = "1.0.0"
source = { editable = "." }
```

### 坑 3: web_search 参数格式不统一

不同模型/runtime 的 web_search tool_call 参数格式不同：

| 格式 | 来源 | 示例 |
|------|------|------|
| `{"queries": ["q1", "q2"]}` | AI_Platform (kosong) | 数组，多个搜索词 |
| `{"query": "q1"}` | 其他模型 | 单个搜索词 |
| `{"q": "q1"}` | 简写 | 偶见 |

脚本必须同时处理所有格式。参考实现见 `scripts/judge/web_search_timeliness_judge.py` 的 `_extract_queries_from_args()`。

### 坑 4: Observation 字段是对象不是字典

`fetch_trace()` 返回的 observations 是 Langfuse SDK 对象，用 `getattr()` 而不是 `dict.get()`：

```python
#  错误
obs_name = obs.get("name", "")  # AttributeError

#  正确
obs_name = getattr(obs, "name", "")
```

但 observation 的 `input` 和 `output` 字段是普通 dict，可以正常 `.get()`。

### 坑 5: Score 写到 source batch 的 trace 上

Judge scores 写在 source batch 的 Langfuse traces 上，不在 judge batch 上。查分数用 source batch ID：

```bash
node Platform.mjs scores --batch <sourceBatchId>
```

---

## 输出格式

Score 输出为 JSON 数组，每个元素一个打分维度：

```json
[
  {
    "name": "score_config_name",
    "value": 0.8,
    "data_type": "NUMERIC",
    "comment": "理由"
  },
  {
    "name": "gsb_comparison",
    "value": "Good",
    "data_type": "CATEGORICAL",
    "comment": "Source 更好因为..."
  }
]
```

字段名灵活匹配（`name`/`metric`/`score_name`、`value`/`score`/`result`、`comment`/`reason`/`explanation`），但推荐统一用 `name`/`value`/`comment`。

`data_type` 可选：`NUMERIC`、`BOOLEAN`、`CATEGORICAL`。

---

## 更新 Script Config

```bash
# 查询
curl "https://platform.internal.ai.com/api/script-configs?name=my_judge" \
  -H "X-AuthGateway-Access-Token: $AuthGateway_ACCESS_TOKEN"

# 更新脚本
curl -X PATCH "https://platform.internal.ai.com/api/script-configs/my_judge.py" \
  -H "X-AuthGateway-Access-Token: $AuthGateway_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"script": "..."}'

# 删除
curl -X DELETE "https://platform.internal.ai.com/api/script-configs/my_judge.py" \
  -H "X-AuthGateway-Access-Token: $AuthGateway_ACCESS_TOKEN"
```

---

## 参考实现

| 文件 | 用途 |
|------|------|
| `scripts/judge/web_search_timeliness_judge.py` | 搜索词年份检查 GSB 对比（完整示例，含 Langfuse observation 解析） |
| `eval-judge-modes.md` → Script Judge 章节 | 模式选择和基础示例 |
| `recipes.md` → Script Judge recipe | CLI 跑法速查 |

---

## 开发调试流程

推荐流程：

1. **先用小数据集试跑**：从正式 dataset 随机取 3-5 条，跑 rollout 得到 batch
2. **写脚本 + 上传**：上传到 Platform Script Config
3. **跑 judge dry-run**：确认 payload 正确
4. **跑 judge（5 条）**：看 scores 是否正确
5. **查结果**：`scores --batch <sourceBatchId>` 或直接看 Langfuse trace 上的 scores
6. **迭代**：如果不对，PATCH 更新脚本，重新跑 judge
7. **正式跑**：确认逻辑正确后，跑完整 dataset

调试时看 task 日志可以用：
```bash
node Platform.mjs logs --task <taskId>
```
脚本中的 `print()` 输出会出现在 task 日志里。
