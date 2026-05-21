---
name: Platform-dataset-audit
description: Audit Platform datasets for sensitive keywords. Use when needing to (1) Read Feishu documents containing dataset names, (2) Find corresponding datasets in Platform, (3) Scan dataset items for sensitive keywords like "AI_Platform", "OpenAI-compatible", "msh", "Internal_Tool". Triggers on dataset audit, sensitive word check, Platform dataset scan.
---

# Platform Dataset Audit Skill

Audit Platform datasets for sensitive keywords by reading Feishu documents, finding matching datasets, and scanning all items.

## Workflow

### Step 1: Read Feishu Document

Use `kitty_feishu.KittyFeishuClient` to read the wiki/document:

```python
from kitty_feishu import KittyFeishuClient
client = KittyFeishuClient(session_key)
wiki = client.read_wiki_document(node_token)  # Extract from URL
content = wiki["content"]
```

Extract dataset names from the content (typically in tables or lists).

### Step 2: Find Datasets in Platform

Search for datasets using the Platform API:

```python
import requests
base = "https://platform.internal.ai.com"
headers = {"X-AuthGateway-Access-Token": os.environ["AuthGateway_ACCESS_TOKEN"]}

# Search by name
r = requests.get(f"{base}/api/datasets", headers=headers, 
                 params={"search": dataset_name, "limit": 10})
```

Match dataset names from Feishu with actual Platform dataset names (usually with `_bmk_v0` suffix).

### Step 3: Scan for Sensitive Keywords

Scan all items in each dataset for keywords: `AI_Platform`, `OpenAI-compatible`, `msh`, `Internal_Tool` (case-insensitive).

Use the provided script: `scripts/bmk-scan_keywords.py`

```bash
python scripts/bmk-scan_keywords.py --datasets "ds1,ds2,ds3" --keywords "AI_Platform,OpenAI-compatible,msh,Internal_Tool"
```

Or run programmatically:

```python
from scripts.scan_keywords import scan_datasets
results = scan_datasets(dataset_names, keywords)
```

### Step 4: Report Results

Summarize findings:
- Total items scanned per dataset
- Hit count per dataset
- Keywords found per dataset
- Sample snippets of hits

## Common Patterns

**Feishu Wiki URL format**: `https://internal-docs.company.com/wiki/{node_token}`

**Dataset name mapping**:
- Feishu: `Chat_withtools_写作_text`
- Platform: `Chat_withtools_写作_text_bmk_260116_v0`

**Typical hit locations**:
- `/mnt/AI_Platform/upload/...` paths (vision datasets)
- `mshtools-*` tool call IDs and function names
- `/mnt/Internal_Toolomputer/...` paths (file operations)

## Step 5: Replace Sensitive Keywords

Use `scripts/bmk-replace_keywords.py` to batch-replace sensitive keywords in dataset items.

**替换规则**（顺序敏感，长字符串优先）：

| 原文 | 替换为 | 备注 |
|------|--------|------|
| `/mnt/AI_Platform` | `/mnt/agents` | 路径 |
| `/mnt/Internal_Toolomputer` | `/mnt/agents` | 路径 |
| `OpenAI-compatible` | `Apollo` | |
| `OpenAI-compatible` | `apollo` | |
| `Internal_Toolomputer` | `cosmos` | |
| `Internal_Toolomputer` | `Cosmos` | |
| `月之暗面` | `宇宙无敌` | |
| `AI_Platform` | `nova` | |
| `AI_Platform` | `Nova` | |
| `msh` | `orion` | mshtools → oriontools |
| `Msh` | `Orion` | |
| `Internal_Tool` | `Cosmos` | 小写 Internal_Tool 不替换（易误匹配） |

```bash
# 先 dry-run 看看会替换什么
python scripts/bmk-replace_keywords.py --datasets "ds1,ds2" --dry-run

# 按 tag 批量 dry-run
python scripts/bmk-replace_keywords.py --tag "Online_Exp_Withtools_260323" --dry-run

# 确认无误后正式替换
python scripts/bmk-replace_keywords.py --datasets "ds1,ds2"

# 保存替换日志
python scripts/bmk-replace_keywords.py --datasets "ds1" --output replacements.json
```

️ **必须先 `--dry-run`，确认替换内容合理后再正式执行。**

## Step 6: PII 脱敏（个人隐私信息）

线上捞回来的数据可能包含用户的个人隐私信息（PII），上传评测前**必须先脱敏**。

使用脚本 `scripts/data-sanitize_pii.py`，支持检测并脱敏以下类型：

| PII 类型 | 示例 | 脱敏效果 |
|----------|------|----------|
| 身份证号 | `110101199003076543` | `110***********6543` |
| 手机号 | `13812345678` | `138****5678` |
| 邮箱 | `test@example.com` | `t***@example.com` |
| 银行卡号 | `6222021234567890123` | `6222***********0123` |
| API Key / Token | `sk-abcdefg...` | `sk-abc*****...7890` |
| 密码字段 | `password=MySecret` | `password=***REDACTED***` |
| IPv4 地址 | `192.168.1.100` | `192.168.*.*` |

### 本地文件脱敏

```bash
# 1. 先扫描看看有没有 PII
python scripts/data-sanitize_pii.py scan --file data.jsonl

# 2. 脱敏并输出到新文件
python scripts/data-sanitize_pii.py redact --file data.jsonl --output data_clean.jsonl

# 3. 保存扫描报告为 JSON
python scripts/data-sanitize_pii.py scan --file data.jsonl --output report.json
```

支持格式：JSONL、JSON、CSV、纯文本。

### Platform 数据集脱敏

```bash
# 1. 先扫描
python scripts/data-sanitize_pii.py scan --datasets "ds1,ds2"

# 2. dry-run 看看会改什么
python scripts/data-sanitize_pii.py redact --datasets "ds1,ds2" --dry-run

# 3. 确认后正式脱敏（直接 PATCH 回 Platform）
python scripts/data-sanitize_pii.py redact --datasets "ds1,ds2"
```

️ **必须先 `scan` 或 `--dry-run`，确认脱敏内容合理后再正式执行。**

### 建议流程

线上数据进入评测的标准流程：
1. 拉数据（get_message / trace / 埋点等）
2. **PII 脱敏**（`data-sanitize_pii.py scan` → `redact`）
3. 敏感词替换（`bmk-replace_keywords.py`，处理 AI_Platform/OpenAI-compatible 等品牌词）
4. 上传 Platform

---

## Output Format

Report results as a table:

| Dataset | Total Items | Hit Count | Keywords Found |
|---------|-------------|-----------|----------------|
| ds_name | 50 | 106 | AI_Platform |

Include detailed hits with:
- `item_id`: The affected item
- `path`: Field path in the item
- `keywords`: Which keywords matched
- `snippet`: Brief text snippet (truncated)
