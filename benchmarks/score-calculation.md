# 分数计算与[Internal Docs Platform]填表

从 Platform 获取分数、计算汇总、填入[Internal Docs Platform]表格的完整流程。

> Platform CLI 基础操作见 [Platform/SKILL.md](../Platform/SKILL.md)，各评测类型的特殊算分规则见 [evaluation-types.md](evaluation-types.md)。

---

## 支持的评分类型

| 类型 | 说明 | 示例评分项 | 数据结构 |
|------|------|-----------|----------|
| **NUMERIC** | 数值型评分 | 有效信息密度、逻辑、文风\_浮夸 | `{avg, min, max, count}` |
| **CATEGORICAL** | 分类型（含多种分布） | 通用GSB、体感分、identity、底线、Time(year\_*) | Better/Same/Worse、Better/Worse、True/False、True/Null/False |
| **BOOLEAN** | 布尔型（API 较少返回，大多以 CATEGORICAL 下发） |  | `{True, False}` |

## 算分公式

| 类型 | 可能的分布 | 公式 | 示例 | 适用场景 |
|------|-----------|------|------|----------|
| NUMERIC（默认） | avg + count | `avg × count` | avg=2.23, count=20 → **44.60** | Dataset 绑定的 NUMERIC 评分项（除 Toolcall\_Action\_V2 外） |
| NUMERIC（Withtools） | avg | `avg × 100` | avg=0.85 → **85.00** | 仅 Withtools 的 Toolcall\_Action\_V2 |
| CATEGORICAL | Better/Same/Worse 三分类 | `better / (better + worse) × 100` | B=20, W=40 → **33.33** | GSB 对比（️ **不含 Arena**） |
| CATEGORICAL | Better/Worse 二分类 | `better / (better + worse) × 100` | B=20, W=40 → **33.33** | GSB 二分类对比 |
| CATEGORICAL | True/False 二分类 | `true / (true + false) × 100` | T=115, F=5 → **95.83** | identity 等 |
| CATEGORICAL | True/Null/False 三分类 | `true / (true + false) × 100` | T=90, F=10 → **90.00** | 含 Null 的布尔分类 |

>  Better/Same/Worse 公式排除 Same：Same 表示无明显差异，纳入分母会稀释胜率（否则 Same 与 Worse 无差别）。同理 True/Null/False 排除 Null。

> ℹ️ NUMERIC 的 `avg × count` 计算的是**加权总分**（非百分制），用于后续多 Batch 加权平均计算。
>
> ️ **NUMERIC 默认公式是 `avg × count`**。唯一例外：Withtools 的 Toolcall\_Action\_V2 用 `avg × 100`。具体哪些评分项是 NUMERIC 类型，以 Dataset 实际绑定的 score config 为准。

>  **Arena 评测不使用上述 CATEGORICAL 公式**。Arena 的正确公式是 `(Better×1 + Same×0.5 + Worse×0) / 总数 × 100`，详见 [evaluation-types.md §3 Arena 评测](evaluation-types.md#3-arena-评测-️)。使用脚本时加 `--arena` 参数：`python3 scripts/calculate_scores.py --arena <batch_ids>`。
---

## 分数获取流程

### ️ 关键：分数在源 batch 的 trace 上

Judge batch 的分数最终写在 **rollout（源）batch 的 trace** 上，不是 judge batch 本身。因此：

1. **获取 judge batch ID**：rollout batch 完成后，用 `describe --batch <rollout_batch_id>` 查看关联的 judge batch ID。
2. **等待 judge batch 完成**：轮询 `describe --batch <judge_batch_id>` 直到 status 为 completed。
3. **拉取分数**：对 **rollout batch**（而非 judge batch）调用 `scores --batch <rollout_batch_id>`。

### ️ 关键：必须用 traceIds 查询

旧方式用 `datasetRunId` 查询对 NUMERIC 类型会返回空数据。正确方式是先收集 traceIds，再用 traceIds 查询。

### Step 1: 收集 traceIds

```python
def collect_trace_ids(batch_id, token):
    """收集 Batch 的所有 traceIds（与 CLI scores.mjs 逻辑一致）"""
    headers = {'Authorization': f'Bearer {token}'}
    trace_ids = []
    page = 1
    page_size = 200

    while True:
        resp = requests.get(
            f"{ORBIT_API_BASE}/langfuse/dataset-run",
            params={'batchId': batch_id, 'page': page, 'pageSize': page_size},
            headers=headers, timeout=30
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        items = data.get('datasetRunItems', data.get('items', []))
        for item in items:
            if item.get('traceId'):
                trace_ids.append(item['traceId'])
        total_pages = data.get('pagination', {}).get('totalPages', 1)
        if page >= total_pages or len(items) == 0:
            break
        page += 1

    return trace_ids
```

### Step 2: 用 traceIds 获取并解析分数

> ️ **Arena 评测不要用此函数**下面的 CATEGORICAL 分支计算的是 `Better/(Better+Worse)` 胜率，
> 不包含 Same。Arena 的正确公式是 `(Better×1 + Same×0.5) / 总数 × 100`，
> 请使用 [evaluation-types.md](evaluation-types.md#3-arena-评测-️) 中的 `calculate_arena_score()`。

```python
def parse_scores(batch_id, token):
    """解析分数数据  通用版，支持 NUMERIC, CATEGORICAL, BOOLEAN。
    ️ Arena 评测请使用 evaluation-types.md 中的 calculate_arena_score()"""
    headers = {'Authorization': f'Bearer {token}'}

    # 1. 收集 traceIds
    trace_ids = collect_trace_ids(batch_id, token)
    if not trace_ids:
        return []

    # 2. 用 traceIds 查询 score-stats
    resp = requests.get(
        f"{ORBIT_API_BASE}/langfuse/dataset-run/score-stats",
        params={'traceIds': ','.join(trace_ids)},
        headers=headers, timeout=30
    )
    if resp.status_code != 200:
        return []

    scores_data = resp.json()
    all_rows = scores_data.get('byJudgeBatch', {}).get('__all__', {}).get('rows', [])
    results = []

    for row in all_rows:
        score_name = row.get('name', '')
        count = row.get('count', 0)
        data_type = row.get('dataType', '')
        distribution = row.get('distribution', {})

        # NUMERIC
        if data_type == 'NUMERIC':
            avg = row.get('avg', 0)
            final_score = round(avg * count, 2)
            results.append({
                'score_name': score_name, 'data_type': 'NUMERIC',
                'avg_score': avg, 'count': count, 'final_score': final_score
            })

        # CATEGORICAL (Better/Same/Worse 等多分类)
        elif data_type == 'CATEGORICAL':
            if 'Better' in distribution or 'Worse' in distribution or ' Worse' in distribution:
                better = distribution.get('Better', 0)
                # NOTE: Platform API 有时返回 ' Worse'（带前导空格），这是已知的数据 quirk，不是 typo
                worse = distribution.get('Worse', distribution.get(' Worse', 0))
                same = distribution.get('Same', 0)
                total = better + worse  # 排除 Same
                percentage = round(better / total * 100, 2) if total > 0 else 0
                results.append({
                    'score_name': score_name, 'data_type': 'CATEGORICAL',
                    'better': better, 'worse': worse, 'same': same,
                    'percentage': percentage
                })
            elif 'True' in distribution or 'False' in distribution:
                # True/False 二分类 或 True/Null/False 三分类（如 identity）
                true_count = distribution.get('True', 0)
                false_count = distribution.get('False', 0)
                total = true_count + false_count  # 排除 Null
                percentage = round(true_count / total * 100, 2) if total > 0 else 0
                results.append({
                    'score_name': score_name, 'data_type': 'CATEGORICAL',
                    'sub_type': 'BOOLEAN',
                    'true_count': true_count, 'false_count': false_count,
                    'total': total, 'percentage': percentage
                })

        # BOOLEAN  API 较少返回此类型，但保留兼容
        elif data_type == 'BOOLEAN':
            true_count = distribution.get('True', 0)
            false_count = distribution.get('False', 0)
            total = true_count + false_count
            percentage = round(true_count / total * 100, 2) if total > 0 else 0
            results.append({
                'score_name': score_name, 'data_type': 'BOOLEAN',
                'true_count': true_count, 'false_count': false_count,
                'total': total, 'percentage': percentage
            })

    return results
```

---

## 题数完整性检查

每个 Batch 有「完整题数」（totalTasks）。评分项的 count 应等于 totalTasks，否则说明部分 task 评分丢失。

```python
def get_batch_total_tasks(batch_id, token):
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.get(
        f"{ORBIT_API_BASE}/rollout/batches/{batch_id}",
        params={'includeProgress': 'true'},
        headers=headers, timeout=30
    )
    if resp.status_code == 200:
        return resp.json().get('progress', {}).get('totalTasks', 0)
    return 0
```

处理建议：

| 缺失程度 | 处理 |
|----------|------|
| 缺 1-2 题 | 可接受，报告中标注 |
| 缺 >10% | 严重缺失，通知用户，建议重跑 |
| count = 0 | 评分完全失败，不使用该分数 |

---

## 多 Batch 加权平均

```
加权平均分 = Σ positive / (Σ positive + Σ negative) × 100
其中：CATEGORICAL Better/Worse 类 → positive=Better, negative=Worse
      CATEGORICAL True/False 类 → positive=True, negative=False
```

### 分数分类规则

| 分类 | 判定规则 | 示例 |
|------|---------|------|
| 综合体感 (Vibe) | 不属于底线或单向的所有评分项 | text\_vibe\_roleplay, sql改写 |
| 底线 (Baseline) | 名称包含 `底线-` | 底线-Repeat, 底线-不合理拒答 |
| 单向能力 (Single) | 名称包含 `online-单向-` 或 `Online-单向-` | online-单向-reasoning |
| 其他 | 不包含 vibe/底线/单向 | 返回 score name 本身，不带分类 |

```python
def categorize_score_by_content(score_name):
    """根据评分项名称包含的关键词自动分类

    实际 score name 示例: text_vibe_xxx, 底线-Repeat, online-单向-reasoning
    """
    name_lower = score_name.lower()
    if "vibe" in name_lower:
        return 'vibe'
    elif "底线" in score_name:
        return 'baseline'
    elif "单向" in score_name:
        return 'single'
    else:
        return score_name  # 不属于任何分类，直接返回原始名称
```

### 分类汇总计算

```python
def calculate_categorized_scores(scores_df):
    """计算分类总分（Vibe / Baseline / Single Items）"""
    filtered = scores_df[
        (scores_df['data_type'] == 'CATEGORICAL') |
        (scores_df['data_type'] == 'BOOLEAN')
    ]

    score_agg = {}
    for score_name in filtered['score_name'].unique():
        subset = filtered[filtered['score_name'] == score_name]
        # 判断是否为 True/False 类（BOOLEAN 或 CATEGORICAL True/False）
        is_bool = (
            'true_count' in subset.columns
            and subset['true_count'].notna().any()
        )
        if is_bool:
            pos = int(subset['true_count'].sum())
            neg = int(subset['false_count'].sum())
        else:
            pos = int(subset['better'].sum())
            neg = int(subset['worse'].sum())
        score_agg[score_name] = {'positive': pos, 'negative': neg}

    vibe_items, baseline_items, single_items = [], [], []
    for name, agg in score_agg.items():
        if '底线-' in name:
            baseline_items.append(agg)
        elif 'online-单向-' in name or 'Online-单向-' in name:
            single_items.append(agg)
        else:
            vibe_items.append(agg)

    def calc_total(items):
        total_pos = sum(i['positive'] for i in items)
        total_neg = sum(i['negative'] for i in items)
        total = total_pos + total_neg
        pct = round(total_pos / total * 100, 2) if total > 0 else 0.0
        return {'positive': total_pos, 'negative': total_neg,
                'total': total, 'percentage': pct, 'count': len(items)}

    return {
        'vibe': calc_total(vibe_items),
        'baseline': calc_total(baseline_items),
        'single_items': calc_total(single_items),
    }
```

---

## 填入[Internal Docs Platform]表格

**表格地址**：https://internal-docs.company.com/wiki/RT40w1ofXi0W48k4ak3cUjmQn2f
**表格 token**：`DW8gsuAZdhCBact9eQ4cE827nEd`

### Sheet 结构一览

| Sheet | sheet_id | 行含义 | 列含义 | Agent 填写范围 |
|-------|----------|---------|---------|---------------|
| Text | `eb66ff` | Row0=模型, Row1=总分, Row2+=按方向分组的数据集 | A=数据集名, B+=模型 | 填各数据集单项分 + 方向小计 + 总分 |
| Vision | `br4KYy` | 同 Text | 同 Text | 同 Text（填单项分 + 方向小计 + 总分） |
| Arena | `90NqdP` | Row0=模型, Row1=TextArena-实际, Row2=TextArena-校准, Row3=VisionArena-实际, Row4=VisionArena-校准, Row5/8=batch ID | A=指标名, B+=模型 | 只填实际分(Row1/3) + batch ID(Row5/8)，校准分由用户手动填 |
| Tools | `gdvWps` | Row0=模型(每模型占2列), Row1=[得分,调Tool意图行为一致率], Row2=总分, Row3+=数据集 | 每模型 2 列 | 填各数据集的 2 列值 + 总分 |
| 专项 | `t7MY31` | Row0=[空,备注,模型名...], Row1+=数据集 | A=数据集名, B=备注(满分/理想态), C+=模型 | 填各数据集分数，无总分行 |
| Dixian | `IKUtYh` | Row0=模型, Row1=vision, Row2=text | A=方向, B+=模型 | 填 vision/text 两行分数 |
| online底线与单项观测 | `U7EkXn` | Row0=模型, Row1=分类(底线/单项), Row2=维度名, Row3=分数 | 横向展开维度 | 填各维度分数 |

### 专项 Sheet 特殊说明

- **time** dataset 有 4 个子行：`year_all`(Row4)、`year_answer`(Row5)、`year_search`(Row6)、`year_data`(Row7)，每项满分 100
- **identity** 多环境测试另有文档，不在此表填入
- 各专项 dataset 的满分/理想态等以[[Internal Docs Platform]评测总表](https://internal-docs.company.com/wiki/RT40w1ofXi0W48k4ak3cUjmQn2f)中的备注列为准
- 有 fail 的 task 需标注，如 `44.6\nfail：1`

### 填表流程

```python
from kitty_feishu import KittyFeishuClient
client = KittyFeishuClient(session_id='<YOUR_SESSION_ID>')  # 替换为实际 session_id
token = 'DW8gsuAZdhCBact9eQ4cE827nEd'

# 1. 读 Row0 找模型列（没有则追加到右侧第一个空列）
header = client.read_sheet_range(token, 'eb66ff!A1:V1')
# 找到模型名对应的列索引

# 2. 读 A 列找数据集行
rows = client.read_sheet_range(token, 'eb66ff!A1:A30')
# 找到数据集名对应的行号

# 3. 填入分数
client.write_sheet_range(token, 'eb66ff!H3', [[score_value]])

# 4. 验证
data = client.read_sheet_range(token, 'eb66ff!H3')
print(data)
```

### 注意事项

- Range 格式：必须含 sheet\_id 前缀，如 `eb66ff!B3:I3`
- 数据格式：传入二维数组，即使只有一行也要 `[[...]]`
- 填入前先确认模型列和数据集行，避免覆盖其他数据
- 填入后务必读取验证
- **Arena 校准分**由用户手动填，Agent 不填
- 总分行、方向小计行由 Agent 计算后填入

---

##  必须遵守的规则

### 阶段一：数据获取

**规则 1：数据来源必须使用 `__all__` 汇总**

始终读取 `byJudgeBatch.__all__` 的数据，禁止使用单个 judge batch 的数据。

```
 使用单个 judge batch（如 66609）：中文创意写作 Better=1, Worse=6 → 14.29
 使用 __all__ 汇总：中文创意写作 Better=20, Worse=40 → 33.33
```

**规则 2：输出 batch ID**

输出所有 batch 的 batch ID，与数据集、分数一一对应，一起记录在[Internal Docs Platform]表格中。

| 数据集 | Batch ID | vibe 分 |
|--------|----------|---------|
| xxx | 75469 | 94.75 |

### 阶段二：分数计算

**规则 3：遍历所有评分项，不要预设**

```python
#  硬编码评分项
if name in ['year_all', 'year_answer']:

#  遍历所有返回的评分项
for row in rows:
    name = row.get('name', '')
```

> 真实案例：Time 评测最初只填了 year\_all 和 year\_answer，遗漏了 year\_search 和 year\_data。

**规则 4：一个 batch 可能有多个 vibe 评分项**

部分数据集有多个 vibe 评分项（如 pdf吃瓜 有"准确率"+"体感分"），每个需独立计算、独立填表。

### 阶段三：表格填入

**规则 5：填入前确认模型对应关系**

```bash
node Platform.mjs describe --batch <batch_id>
# 查看 config.model 确认模型名称 → 对应表格哪一列
# 如果没有对应列 → 从左往右第一个空白列填入
```

**规则 6：填入前最终核对清单**

| # | 检查项 |
|---|--------|
| 1 |  batch ID |
| 2 |  使用 `__all__` 汇总数据 |
| 3 |  遍历所有评分项 |
| 4 |  多评分项独立计入 |
| 5 |  单 batch 只算 vibe |
| 6 |  确认模型对应正确的列 |
| 7 |  核对计算公式 |
| 8 |  验证填入结果 |

---

## 完整工作流

### 方式一：使用可执行脚本（推荐）

```bash
# 单个 batch 算分
python3 scripts/calculate_scores.py 75469

# 多个 batch 加权平均
python3 scripts/calculate_scores.py 75469 75470 75471

# Arena 模式（使用特殊公式）
python3 scripts/calculate_scores.py --arena 75469 75470

# Toolcall_Action_V2 模式
python3 scripts/calculate_scores.py --toolcall-action-v2 75469

# JSON 输出（方便程序调用）
python3 scripts/calculate_scores.py --json 75469 75470
```

### 方式二：手动执行

```
1. 提取多个 Batch 分数 (parse_scores)
   ↓
2. 聚合成 DataFrame
   ↓
3. 计算分类总分 (calculate_categorized_scores)
   ↓
4. 填入[Internal Docs Platform]表格 (write_sheet_range)
   ↓
5. 验证填入结果 (read_sheet_range)
```
