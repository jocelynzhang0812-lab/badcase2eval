# Benchmarks  评测运行与算分

从接到评测需求到分数填入[Internal Docs Platform]表格的完整流程。**跑评测前先读这里。**

---

## 全局流程

```
① evaluation-types.md   查配置：tag 怎么转、模型 concurrent 多少、这个类型怎么跑
        ↓
② preflight-check.md    跑预检：模型健不健康、花多少钱、余额够不够
        ↓
③ score-calculation.md   算分数：怎么拉分数、怎么加权、怎么填[Internal Docs Platform]表
```

---

## ① 查配置

**文件**: [evaluation-types.md](evaluation-types.md)
**什么时候读**: 每次跑评测前

| 用户说 | → 去哪里 |
|-------|----------|
| "roll 一下 text" / "跑 arena" | → §Tag 别名：用户简称 → Platform 实际 tag |
| "用 opus 跑" / "AI_Platform concurrent 多少" | → §模型别名与部署类型：AI_Platform→自部署(20), 外部→非自部署(5) |
| "开思考用什么参数" / "关思考 temperature 多少" | → §通用默认参数：开/关思考的 temp/max-tokens/top-p |
| "Arena 用什么 prompt" / "空 prompt 怎么配" | → §常用 Prompt：4 个 prompt 名 + 使用场景 |
| "identity 是什么类型" / "逻辑分范围" | → §Score Config 速查：8 个评分项的类型和范围 |
| "text 怎么跑" / "withtools 有什么特殊的" | → §1-8 评测类型：每种类型的运行配置 + 算分规则 |
| "Arena 分数怎么算" / "Toolcall_Action_V2 公式" | → §3 Arena / §5 Withtools：特殊算分函数代码 |
| "Identity 要跑几个 batch" / "Time 多环境怎么配" | → §6 专项评测：Identity 6 batch / Time 3 batch 矩阵 |
| "底线跑几次" | → §7 底线评测：默认运行 3 次取加权平均 |
| "执行流程是什么" | → §执行流程：解析 tag → 定 concurrent → 查数据集 → dry-run → 批量执行 |

---

## ② 跑预检

**文件**: [preflight-check.md](preflight-check.md)
**什么时候读**: dry-run 通过后、正式执行前

| 用户说 | → 去哪里 |
|-------|----------|
| "模型能用吗" / "健康检查" | → §模型健康检查：rollout 模型 + judge 模型逐一检测 |
| "跑一轮要多少钱" | → §成本估算：各方向单价 × 数据集数量 |
| "余额够不够" | → §余额检查：当前余额 vs 预估成本，判定 go/no-go |

---

## ③ 算分数

**文件**: [score-calculation.md](score-calculation.md)
**什么时候读**: 评测跑完、需要算分时

| 用户说 | → 去哪里 |
|-------|----------|
| "拉分数" / "怎么获取分数" | → §分数获取流程：collect_trace_ids → parse_scores |
| "为什么分数是空的" | → §关键：必须用 traceIds 查询（旧方式 datasetRunId 对 NUMERIC 返回空） |
| "题数对不上" / "缺了几题" | → §题数完整性检查：缺失程度 vs 处理建议 |
| "多个 batch 怎么合" | → §多 Batch 加权平均 |
| "vibe / 底线 / 单向 怎么分" | → §分数分类规则：categorize_score_by_content() |
| "分数填到哪" / "[Internal Docs Platform]表格" | → §填入[Internal Docs Platform]表格：地址 + 代码示例 + 注意事项 |
| "算分有什么规矩" | → §必须遵守的规则：8 条（__all__ 汇总、遍历所有评分项、填入前核对） |

---

## 数据集规范

### 目录结构

```
benchmarks/
├── README.md                ← 本文件
├── evaluation-types.md      ← ① 评测配置与类型规格
├── preflight-check.md       ← ② 运行前预检
├── score-calculation.md     ← ③ 算分与填表
└── <benchmark_name>/        ← 数据集子目录（按需创建）
    ├── README.md            ← 数据集说明：来源、字段定义、版本历史
    ├── v0.jsonl             ← 数据文件（Platform JSONL 格式）
    └── attachments/         ← 图片等附件（Vision 数据集）
```

### 命名

- **Platform 数据集名**: `{Category}_{场景}_{text/vision}_bmk_v{N}`（例: `Chat_withtools_复杂搜索_text_bmk_v0`）
- **本地目录名**: 简短英文，`-` 分隔（例: `complex-search-text/`）

### 必要字段

| 字段 | 必须 | 说明 |
|------|------|------|
| `input.messages` |  | OpenAI 格式对话 |
| `input.key_point` | 推荐 | 标准答案要点（供 Judge 参考） |
| `input.baseline_model_response` | GSB 必须 | GSB 对比评分的基线回答 |
| `metadata.tags` | 推荐 | 维度标签，便于筛选分析 |
| `metadata.primary_tag` | 推荐 | 主分类标签 |
| `metadata.difficulty` | 可选 | 难度标记 |

详细格式见 [data-csv-to-Platform.md](../references/data-csv-to-Platform.md)。

### 版本管理

- 已上传到 Platform 的数据集**不改已有版本**
- 需要改 → 新版本（v1, v2, ...），README 中记录变更
- 旧版本保留，确保历史 Batch 结果可追溯
