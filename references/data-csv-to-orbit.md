# CSV → Platform 数据格式转换

将各种来源的数据转换为 Internal Evaluation Platform接受的 Dataset 格式。

---

## 输入格式

### 来源 1：[Internal Docs Platform] bitable 导出

从 badcase 多维表格导出的记录（参考 [data-badcase-flow.md](data-badcase-flow.md)）。

### 来源 2：构造好的 BMK CSV/JSONL

```csv
query,rubric,scenario,difficulty
帮我查一下最近关于AI监管的新闻,搜索词应包含时间限定词；结果需包含3条以上近一周新闻,search,medium
```

### 来源 3：已有 BMK 文件

支持中文列名（脚本自动映射）：`问题` → query，`打分点` / `ground_truth` → rubric，`场景` → scenario，`难度` → difficulty

---

## Platform Dataset 格式

### JSONL（推荐）

```jsonl
{"query": "帮我查AI监管新闻", "rubric": "搜索词含时间限定；3条以上新闻", "scenario": "search", "difficulty": "medium", "source_chat_id": "abc123", "source_turn_step": "22-1"}
```

### Excel（[Internal Docs Platform]表格直接导出）

列名用英文，字段相同。

### 字段类型

| 类型 | 说明 | 典型字段 |
|------|------|----------|
| **Input** | 可以在 Rollout Prompt 模板中通过 `{{字段名}}` 引用。**Prompt 里要用到的字段必须放 Input** | `query`, `rubric`, `ground_truth` |
| **Metadata** | 不能在 Prompt 中引用，**只用于筛选和分组** | `scenario`, `difficulty`, `source_chat_id` |

> ️ **判断标准：这个字段会在 Rollout Prompt 里被 `{{}}` 引用吗？**
> - 会 → 放 **Input**
> - 不会，只用来筛选/分组 → 放 **Metadata**
>
> **注意**：Platform LLM/Agent Judge 的 trajectory 是自动注入的，Judge Prompt 里**不需要** `{{query}}` 或 `{{response}}` 等模板变量。只有 Rollout Prompt 才用 `{{}}`。

>  **字段名大小写敏感**：Prompt 模板变量 `{{query}}` 只匹配 Input 中的 `query`（小写），**不会**匹配 `Query`（大写）。上传数据集时务必确认字段名大小写与 Prompt 模板一致，或用 `--field-mapping` 的 `renames` 功能重命名。

---

## 转换脚本

脚本在 `scripts/` 下，支持中文列名自动映射：

```bash
# 通用 CSV → JSONL
python scripts/data-csv_to_orbit.py input.csv [output.jsonl]

# Badcase 表 + trace → JSONL（需先拉 trace）
python scripts/data-badcase_to_orbit.py badcase.csv [output.jsonl]

# [Internal Docs Platform]多维表格 → JSONL 或直接上传
python scripts/data-bitable_to_orbit.py <url> [--field-map '问题:query,评判标准:rubric'] [-o output.jsonl]
python scripts/data-bitable_to_orbit.py <url> --upload --dataset-name <name> --input-fields query,rubric
```

---

## 上传到 Platform

```bash
# 直接上传
node Platform.mjs upload --file dataset.jsonl --dataset "my-benchmark" --dry-run

# 带字段映射
node Platform.mjs upload --file dataset.jsonl --dataset "my-benchmark" \
  --field-mapping '{"inputFields":["query","rubric"],"metadataFields":["scenario","difficulty","source_chat_id","source_turn_step"]}' \
  --dry-run
```

也可以在 Web UI 上传：Platform → Datasets → Upload New Dataset。

---

## 上传后校验

上传完成后**必须**校验数据一致性。支持多种数据源对比：

```bash
# 对比本地文件（CSV/JSONL/XLSX）
python scripts/data-verify_upload.py --dataset <name> --file <path>

# 对比[Internal Docs Platform] bitable（自动调 bitable_to_orbit.py 导出再比）
python scripts/data-verify_upload.py --dataset <name> --bitable <url> [--field-map "问题:query"]

# 对比 trace JSON（自动调 trace_to_orbit.py 导出再比）
python scripts/data-verify_upload.py --dataset <name> --trace <path> [--turn 0]

# 对比另一个 Platform dataset
python scripts/data-verify_upload.py --dataset <name> --source-dataset <other_name>

# 无数据源 → 只检查 dataset 自身
python scripts/data-verify_upload.py --dataset <name> [--expected-count 330]
```

校验项：

| 场景 | 检查内容 |
|------|----------|
| 始终执行 | 条数、字段列表、空值统计、key field 重复检测 |
| 有数据源时额外 | 条数对比、key field 集合对比（找出仅 Dataset 有 / 仅数据源有的） |

示例输出：
```
 条数一致: 330
 query 集合完全匹配（330 个唯一值）
 query 无重复（330 个唯一值）
️  空值字段:
   type: 12/330 条为空
 校验通过！
```

> 数据源四选一（`--file` / `--bitable` / `--trace` / `--source-dataset`），都不传则只检查 dataset 自身。key field 默认 `query`，可用 `--key-field` 指定。

---

## 注意事项

1. **字段名用英文**：合法标识符（字母、数字、下划线）
2. **query 必须存在**：Platform 的必需字段
3. **rubric 需和 Prompt 对应**：Prompt 里写了 `{{rubric}}`，Dataset 里必须有 rubric 列
4. **去重**：转换前检查是否有重复 query

---

## 附件处理

数据上传和附件上传是**分两步**的。

**Step 1：上传数据（文本部分）**
```bash
node Platform.mjs upload --file dataset.jsonl --dataset "my-benchmark" \
  --field-mapping '{"inputFields":["query","rubric","attachment"]}'
```

**Step 2：上传附件文件（CLI）**

```bash
# 先预览匹配情况
node Platform.mjs upload-attachments --folder ./attachments --dataset "my-benchmark" \
  --match-field "attachment" --dry-run

# 确认后执行上传
node Platform.mjs upload-attachments --folder ./attachments --dataset "my-benchmark" \
  --match-field "attachment"
```

参数说明：
- `--folder`：附件文件夹路径，会递归扫描所有文件
- `--match-field`：dataset item 中包含文件名的字段（如 `attachment`、`file`）
- `--target-field`：存储位置，默认 `__orbit_attachments`，也支持 `__orbit_output_files`
- `--inspect-only`：服务端 dry run，检查已有匹配但不上传
- `--dry-run`：客户端预览，显示将要上传的文件列表

️ 每个文件的 basename 必须唯一（不同子目录下不能有同名文件）。

> **[Internal Docs Platform]多维表格的附件**：只有**多维表格**能正确导出附件，普通数字表格不行。
