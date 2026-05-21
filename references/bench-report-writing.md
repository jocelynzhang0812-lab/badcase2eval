---
name: bench-report-writing
description: |
  Platform 评测报告写作。教你怎么用 5 段结构 + 4 类图 + [Internal Docs Platform]段落-图混排 写一份不和稀泥的评测分析。
  Triggers on: eval report, Platform eval report, 测评报告, 评测分析, 评测分析报告,
  by-task 分析, sft 对比, baseline 对比, 评测文档, 评测总结.
---

# Eval Report  写作指南

写一份评测分析时用这个 skill。重点是**怎么写**:结构、语言、图文混排。数据怎么拉、Platform 怎么起任务**不在这个 skill 范围**(那是 `eval-skill` / `Platform` 的事)。

> 写[Internal Docs Platform] doc 之前先看[Internal Docs Platform]排版风格 skill,用[Internal Docs Platform] doc skill 推到[Internal Docs Platform]。

---

## 0. Example(必看)

直接拿这份对照着写,比读这个 skill 都快:

| 文件 | 用途 |
|---|---|
| **[Internal Docs Platform] doc** [`docx/AxLjdCRmvoQPmMxMDeYcCGeCnag`](https://internal-docs.company.com/docx/AxLjdCRmvoQPmMxMDeYcCGeCnag) | 最终成品。看段落-图混排怎么排、callout 怎么用、表格怎么做 |
| **画图脚本** `scripts/bench-report/plot_*.py` | 4 个 plotly 脚本,改顶部 `BATCHES` dict 就能跑出 example 同款图 |

---

## 1. 5 段结构(顺序不要变)

每份评测报告固定 5 段,缺一不可:

```
TL;DR (callout)
   ↓
实验设置 (一张表)
   ↓
Part 1: By Model  模型行为
   ↓
Part 2: By 题目类型  难度与稳定性
   ↓
Part 3: By 题目  异常题 trace 审查
   ↓
Action Items
```

### 1.1 TL;DR Callout

放在最顶。**强制回答 4 个问题**,每个问题一行,带数字:

```markdown
<callout emoji="bar_chart" background-color="light-blue">
**TL;DR**
**哪个模型更好**: <一句话结论 + 数字>
**比 baseline 怎么了**: <相对 baseline 涨/跌的类别 + 数字>
**模型行为**: <稳定性 / 方差 / 异常>
**有问题的题**: <环境 bug / rubric 天花板 / 已修 commit>
</callout>
```

**纪律**:
- 不能比 baseline 强就直说,**别和稀泥**(`基本持平` `略有提升` 这种话不能用)
- 提数字必须带 ±σ
- 有 commit 写 commit hash,有题写题名,读者能直接点

### 1.2 实验设置

一张表 + 1 行附注。

| 字段 | 例 |
|---|---|
| 模型 | `model-v3` |
| 角色 | `baseline` / `待评 A` / `upper baseline` |
| runs | `5`(sft 至少 5,opus 1 也行) |
| batch_ids | `batch_abc, batch_def`(Platform batch) |
| Overall | `0.564±0.034`(mean±σ,3 位) |

附注 1 行写题数分布 + judge 模型: `78 题分布:TypeA 16 / TypeB 13 / TypeC 10 / TypeD 16 / Other 23。Judge 用 gpt-5.4。`(类别名按实际评测集替换)

### 1.3 Part 1: By Model  模型行为分析

**目的**: 看每个模型在不同类别的均值和稳定性。**这部分最长**,因为是核心结论的支撑。

#### 必含子节(顺序)

1. **怎么读图**(每份报告都要写,读者第一次见图)
   ```markdown
   实线 = 每轮 run 实际得分,虚线 = 多轮均值,色带 = ±1σ。
   <text bgcolor="light-yellow">**色带越宽,模型在这类题上行为越不确定**</text>
   同样的题跑多次结果差异大。opus 只跑 1 次没色带,作为 upper baseline 参考。
   ```
   *没这一段读者会把色带当 confidence interval,误读成统计显著性。*

2. **Overall**  1 张图 + 1 段解读。图来自 `plot_bmk.py` 第一张。
3. **分类别**  1 张图(N 类 facet) + 1 张表 + 1 个 Insight callout。图来自 `plot_bmk.py` 第二张。
4. **类别对比表必须有 Δ vs baseline 列**,例:
   ```
   | 类别 | baseline | candidateA | candidateB | upper | A vs baseline |
   | TypeA (16) | 0.592±0.042 | 0.631±0.079 | ... | 0.701 | **+0.039** |
   | TypeB (13) | **0.790±0.029** | 0.653±0.049 | ... | 0.737 | **-0.137** |
   ```
   涨跌的数字加粗,正负都加粗。
5. **Insight callout**  一句话点出 trade-off,例:`sft 的 trade-off:TypeA/TypeC 提升,TypeB 退化 -0.14。Overall 持平是因为两边抵消了。`
6. **(可选)sft 内部对比**  多个候选时用 `plot_compare.py` 出左右两张图。

### 1.4 Part 2: By 题目类型  难度与稳定性

**目的**: 离开模型视角,从题目侧看分布。

#### 必含子节
1. **Difficulty 梯度表**  easy/medium/hard 题数 + 全模型平均分
2. **各类别得分表**  N 类的题数 / 平均分 / 0 分题数
3. **方差排名图**  `plot_variance.py` 输出,1 张图(或每类 1 张)。配 1 段解读: 哪类题方差最大(binary outcome 类题天然方差大)
4. **全 0 题列表**  全模型全 run 都 0 的题,**列表 + 一句话**: `16 次全 0,不具备区分度`

### 1.5 Part 3: By 题目  异常题 Trace 审查

**目的**: 把 Part 2 标出的"异常"用具体原因解释,**别停留在'分低'**。

异常分 3 类,每类用不同 callout 颜色:

#### A. 环境 bug(`light-red` + )

```markdown
<callout emoji="bug" background-color="light-red">
**task-fetch-data(全模型低分约 0.13)**  agent 缺少必要工具,只有 3 个基础工具,完全没有 search/read/exec。
根因:prompt 配置遗漏了工具注册。已修复 commit `2ddcbb8`。
</callout>
```

**3 件事必写**: 现象 / 根因 / 修法(commit hash 或 PR 号)。

#### B. Rubric 天花板(普通段落)

```markdown
**task-verify-secret  永远 0.6**:所有模型都答对了,但 rubric 要求显式认出+知道在被验证。
```

决策放最后: 放宽 rubric / 降权重 / 接受现状。

#### C. 行为随机(普通段落)

```markdown
**task-write-info  σ=0.43**:写了 1.0,不写 0.0,binary outcome。
```

可不修,但要标方差大不能用作单 run 判断。

#### Trace 引用图文混排

异常题如果有截图(agent payload / tool 列表 / trace 截图),用 `<grid cols="2">` 左右拼:

```markdown
<grid cols="2">
  <column width="51">
    <image token="..." width="974" height="940" align="center"/>
  </column>
  <column width="48">
    <image token="..." width="2158" height="2180" align="center"/>
  </column>
</grid>
```

### 1.6 Action Items 表

| 优先级 | 问题 | 题目 | 建议 |
|---|---|---|---|
| **P0** | 环境 bug | task-fetch-data | 已修, MR 待 merge |
| **P1** | sft TypeB 退化 | TypeB-* (13 道) | sft 数据需关注 TypeB 覆盖 |
| **P2** | rubric 天花板 | verify-secret / release-decision | 放宽 check 或降权重 |

**P0 = 环境/工具问题(必修)** / **P1 = 模型能力问题(下版本目标)** / **P2 = rubric 优化(可选)**。
不要把所有事都标 P1。

---

## 2. 4 张图怎么用

脚本都在 `scripts/bench-report/`,**直接 cp 到你的 review 目录**,改顶部 `BATCHES` dict 即可。脚本本身不用读懂。

| 脚本 | 用在哪段 | 输出 | 改什么 |
|---|---|---|---|
| `plot_bmk.py` | Part 1 (Overall + 分类别) | 2 张图 PNG/HTML | `BATCHES = {model: [batch_ids]}` |
| `plot_compare.py` | Part 1 (sft 对比, 可选) | 1 张左右图 | 同上 |
| `plot_task_view.py` | Part 2 (by-task 共性) | N 张 task scatter | 同上 |
| `plot_variance.py` | Part 2 (方差) | N 张 σ 排名图 | 同上 |

```python
BATCHES = {
    'baseline':        ['batch_abc_run1', 'batch_abc_run2', ...],   # ← 改这里
    'candidateA-sft':  ['batch_def_run1', 'batch_def_run2', ...],
    'upper-baseline':  ['batch_ghi'],
}
```

`AuthGateway_ACCESS_TOKEN` 从 env 读,不用改。`COLORS` / `CATEGORIES` 默认就行,有特殊需求再调。

---

## 3. 写作语言

报告是给 reviewer 看的,**不是博客**。语言纪律:

### 3.1 用数字代替形容词

```
 candidateA 在 TypeA 题上有显著提升
 candidateA 在 TypeA 题上 +0.039(0.592→0.631),色带 σ=0.079 比 baseline 宽近一倍
```

### 3.2 trade-off 必须双面写

```
 sft 整体表现不错
 sft 的 trade-off:TypeA/TypeC 涨了 +0.04/+0.09,TypeB 退化 -0.14,Overall 持平是抵消了
```

### 3.3 异常必须给 root cause

```
 task-fetch-data 三模型都低分,可能模型能力不够
 task-fetch-data 全模型 0.13,根因是 prompt 配置遗漏了工具注册 → agent 只有 3 个基础工具,
   完全没有 search/read/exec。已修 commit 2ddcbb8。
```

### 3.4 别用模糊词

禁用清单: `基本持平`、`略有提升`、`整体来看`、`从某种程度上`、`可能存在`、`一定程度上`。

允许用 `持平 ±σ 内` / `+0.04 内涨幅` / `根因明确为 X`。

### 3.5 段落短

一段 ≤ 3 行。表格 + 图 + 段落穿插,**不写超过 5 行的纯文字段**(读者跳过)。

---

## 4. [Internal Docs Platform]图文混排

[Internal Docs Platform] doc 不是 markdown。**段落 → 图 → 段落** 是基本节奏。每个图前后都要有解读文字。

### 4.1 单图

```markdown
### Overall

baseline 和 candidateA 均值完全重叠(0.564)。candidateA 色带略宽(σ=0.039 vs 0.034),行为稳定性稍弱。

<image token="NOdRbQF8goakPjxWy2Tcjvxtnnh" width="1300" height="900" align="center"/>

candidateB 均值更低(0.552)但色带最窄(σ=0.016),最稳定但天花板也最低。
```

**图前一段说"图想看什么"**,图后一段说"看完得到什么"。**不要把图甩在段落末尾**。

### 4.2 表 + 图 + Insight callout 三件套(Part 1 类别对比的标准模板)

```markdown
### 分类别

<image token="FYwrbqo6GojSE7xvBeqc537pnei" width="1900" height="1640" align="center"/>

<lark-table rows="6" cols="6" header-row="true">...类别对比表...</lark-table>

<callout emoji="bulb" background-color="light-yellow">
**Insight**  sft 的 trade-off:TypeA/TypeC 涨了,TypeB 退化 -0.14...
</callout>
```

图 → 表(展开数字) → callout(收口结论)。这个三件套用于 Part 1 的核心论点。

### 4.3 左右图(Part 3 trace 截图)

`<grid cols="2">` + `<column>` 嵌套,见 1.5 节。两张截图并排,左边 agent 行为/输出,右边 trace/工具列表对比。

### 4.4 上传图拿 token

```bash
lark-cli docs +media-insert --doc <doc-token> --file <png-path>
```

返回的 `image_token` 替换 `![alt](file.png)` → `<image token="<token>" width="W" height="H" align="center"/>`。

---

## 5. 落盘约定

每次 review 单独建目录:

```
<project>/<MMDD>review/
├── review.md                          # 本地 markdown 草稿
├── feishu_doc.md                      # [Internal Docs Platform]化版本(lark-* 标签 + image token)
├── plot_*.py                          # 4 个画图脚本(改了 BATCHES dict)
├── <prefix>_overall.png               # 输出图
├── <prefix>_categories.png
├── ...
└── traces/                            # (可选) trace 截图素材
```

`<MMDD>` = `0409review` `0410review`。脚本 + 数据 + 图全捆绑,以后能复现。

---

## 6. Common Pitfalls

| 坑 | 修法 |
|---|---|
| TL;DR 写"总体表现良好" | 写不出数字就别写 TL;DR  重新看数据 |
| 类别表没 Δ 列 | 加上,正负都加粗 |
| Part 1 没 "怎么读图" 段 | 加上,色带宽度 = 行为不确定性这句必须有 |
| 异常题只写"分低"不给 root cause | 拉 artifact 看 trace,定位 → 工具缺 / prompt 错 / rubric 卡 |
| 把所有事都标 P1 | 严格区分 P0/P1/P2 |
| [Internal Docs Platform] doc 把图全堆在末尾 | 图前后都要有解读 1-2 句 |
| sft 只跑 1 次就下结论 | sft ≥ 5 次,baseline ≥ 5 次,upper baseline 1 次做参考 |

---

## 7. 写完之后

1. **草稿 review**  自己读一遍,Pitfalls 表对照。重点看 TL;DR 数字、Δ 列、root cause。
2. **画图脚本入仓**  `<MMDD>review/plot_*.py` 跟着 review.md 一起提交,保证可复现。
3. **[Internal Docs Platform]化**  用[Internal Docs Platform] doc skill 创建文档,标题格式: `[<Team>] <Benchmark> v<VER> 评测分析`
4. **同步 worklog**  worklog 加一行: `### <Benchmark> v<VER> Review (<MMDD>)` + [Internal Docs Platform] doc 链接 + Action Items 摘要

---

## Reference

- **Example [Internal Docs Platform] doc**: https://internal-docs.company.com/docx/AxLjdCRmvoQPmMxMDeYcCGeCnag
- **画图脚本**: `scripts/bench-report/plot_*.py`
- **数据获取 / 跑任务**: `eval-skill` 或 `Platform` skill
