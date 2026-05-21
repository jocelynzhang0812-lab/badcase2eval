# Bad Case to Eval-Skill

从发现 badcase 到构造 benchmark、跑评测、分析结果的完整闭环。给 AI Agent 用的 skill，也可以人工按流程操作。

## 核心流程

```
发现 badcase → 拉 trace → 对照价值观 → 收录到 bitable
    → 复现验证（Platform 跑 10 次）→ 确认进入 bmk
        → 跑评测（Platform CLI）→ Judge → 分析结果 → 持续观测

数仓批量挖掘：Insight SQL → [Internal Docs Platform]多维表格 → 拉 trace → 标注 → Platform 数据集
反馈分析：Feedback 数据库 → 查询点赞/点踩 → 归因分析
```

## 快速开始

>  **第一次跑评测？** 看 [examples/QUICKSTART.md](examples/QUICKSTART.md)  10 分钟端到端教程。

```bash
pip install -r requirements.txt       # 安装依赖
cp .env.example .env                  # 填入 AuthGateway_ACCESS_TOKEN / OPENAI_API_KEY 等
source .env && python scripts/rollout-setup_aksk.py  # 一键配置 Platform AKSK
python scripts/rollout-run_eval.py            # 交互式跑评测
```

Key 获取方式：
- `AuthGateway_ACCESS_TOKEN`: [创建 Personal Token](https://internal.company.com/tokens/user-token-list)
- `OPENAI_API_KEY`: [Internal_AI_Service Staff API Key 使用指南](https://internal-docs.company.com/wiki/GtxdwTKG5ikbXukjQP4cSXIXnBd)
- `ANTHROPIC_API_KEY`: 和 `OPENAI_API_KEY` 一样
- `SEARCH_TOKEN`: [Search 服务(v3版)鉴权&限流](https://internal-docs.company.com/wiki/I5WxwRvlDirliokQ0EUc9KOhnGe)
- `DATASOURCE_KEY`: 找 [Colleague Name 2]老师获取（data_source 系列工具需要）
- `QUERY_ENGINE_API_KEY` / `QUERY_ENGINE_API_SECRET`: 联系 **[Colleague Name 3]** 申请（数仓查询 + 反馈查询）

## 仓库结构

```
├── SKILL.md                          Agent 入口（路由表，匹配用户意图 → 执行）
├── benchmarks/                       Benchmark 数据集 & 评测小抄
│   ├── README.md                         数据集命名规范、字段设计指南
│   ├── evaluation-types.md               8 种评测类型规格（运行配置 + 算分规则）
│   ├── score-calculation.md              评分获取与计算全流程（3 种类型、加权平均、[Internal Docs Platform]填表）
│   └── preflight-check.md                运行前预检（模型健康、成本估算、余额检查）
├── examples/                         快速入门 & 示例文件
│   ├── QUICKSTART.md                     端到端评测教程（10 分钟上手）
│   ├── cli-session.md                    真实 CLI 操作记录
│   ├── sample-dataset.csv                CSV 数据集示例
│   ├── sample-judge-prompt.md            完整 Judge Prompt 示例
│   └── sample-report.md                  评测报告模板
├── data-assistant/                   数据查询助手（ODPS/Hologres 查询、智能 SQL、数据导出）
│   ├── scripts/
│   │   ├── explore_table.py              表结构探查
│   │   ├── get_user_email.py             获取用户邮箱
│   │   └── query_engine_client.py        查询引擎客户端
│   ├── references/
│   │   ├── add_table_workflow.md          添加新表流程
│   │   ├── hologres_mapping.md           Hologres 语法映射
│   │   └── query_engine_client.md        客户端完整文档
│   ├── table_schemas/                    人工维护的表定义（22 张表）
│   ├── SKILL.md                          Data Assistant 入口
│   ├── pyproject.toml
│   └── VERSION
├── Platform/                            Platform CLI  评测平台命令行工具
│   ├── commands/                         CLI 命令（30 个：run/judge/arena/export/...）
│   ├── lib/                              共享库（client/payload/resolve/...）
│   ├── references/                       API 文档 & 使用指南
│   │   ├── api.md / api-shapes.md / openapi.json
│   │   ├── run.md / judge.md / arena.md
│   │   └── debug.md / recipes.md / multi-env-test.md
│   ├── SKILL.md                          Platform Skill 入口
│   └── Platform.mjs                         CLI 主入口
├── references/                       方法论 & 操作指南
│   ├── getting-started.md                 ⓪ 从零创建 Benchmark（8 步引导）
│   ├── data-badcase-flow.md               Badcase 完整链路：发现 → 收录 → 复现 → 进 BMK
│   ├── data-badcase-to-bmk.md             badcase → benchmark 数据集（打标、rubric、变异）
│   ├── data-insight-flow.md                从线上数仓 SQL 批量挖 badcase（Insight 链路）
│   ├── data-feedback-db.md                 Feedback 数据库检索（点赞/点踩/订阅反馈）
│   ├── data-csv-to-Platform.md               CSV/JSONL/Excel → Platform 格式转换
│   ├── data-volc-event-logs.md            火山埋点查询（事件列表、使用场景、分析流程）
│   ├── insight-sql/                        数仓 SQL 模板（按挖掘主题沉淀）
│   ├── bmk-validity.md                    数据质量验证（两个硬门槛）
│   ├── bmk-dataset-audit.md               数据集敏感词审计 & 替换规则
│   ├── eval-judge-modes.md                Judge 三种打分模式 + prompt 模板
│   ├── eval-script-judge-guide.md         Script Judge 开发指南（从零写脚本）
│   ├── eval-trajectory.md                 推理轨迹评测（搜索词、tool_call、引用）
│   ├── eval-review-Platform-results.md       结果分析（分数、归因、Judge Review、报告模板）
│   ├── Internal_Tool-trajectory-troubleshooting.md  Internal_Tool 产出物问题排查（PPT/网页/文档）
│   ├── eval-tool-usage-examples.md        工具使用示例
│   ├── eval-x35-tool-guidelines.md        x35 工具指南
│   ├── bench-report-writing.md            [Internal Docs Platform]评测报告写作（5 段结构 + 图文混排）
│   ├── rollout-Platform-guide.md             Platform 入门指南（Preset/Prompt/Model/Tools/Judge）
│   ├── Platform-interaction-principles.md    交互原则（确认规则、DO/DON'T、红线）
│   └── Platform-score-coverage.md            评分项覆盖情况统计脚本
├── scripts/                              所有脚本（按前缀分组）
│   ├── data-get_message.py               从 chatlet 捞 trace（支持 share link / --agent 精简版）
│   ├── data-fetch_chat_requests.py       拉 Workflow Semantic Trace（Agent Step 级别）
│   ├── data-get_full_trajectory.py       拉完整轨迹（含所有中间步骤）
│   ├── data-kimi_model.py                Internal_Tool 内部工具（对话轨迹 + 文件获取）
│   ├── data-query_feedback.py             Feedback 数据库检索（feedback/subscription/Internal_Tool 表）
│   ├── data-bitable_to_orbit.py          [Internal Docs Platform]多维表格 → Platform
│   ├── data-csv_to_orbit.py              CSV → Platform JSONL
│   ├── data-badcase_to_orbit.py          badcase 表 + trace → Platform 数据集
│   ├── data-trace_to_orbit.py            从 trace 构造 Platform dataset + prompt
│   ├── data-bloom_generate.py             Bloom 自动生成评测场景
│   ├── data-bloom_rollout.py              双模型多轮对话评测
│   ├── data-ask_llm.py                   批量 LLM 打标/分类（并发 + 断点续传）
│   ├── data-query_buried_point.py         查询用户操作埋点（按 user_id/时间/会话ID）
│   ├── data-sanitize_pii.py               PII 脱敏（身份证号、手机号、密码等）
│   ├── data-verify_upload.py              上传校验（--file / --bitable / --trace / --source-dataset）
│   ├── bmk-scan_keywords.py               扫描数据集敏感词
│   ├── bmk-replace_keywords.py            批量替换数据集敏感词
│   ├── bmk-registry.py                    Benchmark 注册表
│   ├── bmk-compare_web_ui.py             逐条并排对比 UI
│   ├── rollout-run_eval.py                交互式评测全流程
│   ├── rollout-setup_aksk.py              一键配置 Platform AKSK
│   ├── rollout-batch_chatty.py           批量跑 Chatty
│   ├── rollout-replay_chatty.py          单条 trace 重放
│   ├── rollout-replay.py                 多条 trace 批量重放
│   ├── eval-judge_trajectory.py          Trajectory Judge（评 tool_call 质量）
│   ├── eval-fact_check.py                FactCheck 事实核查
│   ├── eval-analyze_trajectory.py        Agent 轨迹分析
│   ├── eval-export_batch_csv.py          导出 batch 为 7 列 CSV
│   ├── batch_monitor.py                   Batch 状态监控（--watch/--check，>20% 失败告警）
│   ├── dataset_tag_indexer.py            ️ 数据集 Tag 索引（--build/--find/--list-tags）
│   ├── bench-report/                      评测报告生成脚本
│   ├── judge/                            LLM Judge 打分（Chatty 链路）
│   ├── bmk/                              两组结果统计对比
│   └── preset/                           预设配置
├── .env.example                      环境变量模板
├── requirements.txt                  Python 依赖 + Platform CLI 安装说明
└── config.example.yaml               路径配置
```

## 关键门槛

| 门槛 | 标准 | 含义 |
|------|------|------|
| 复现率 | ≥ 1/10 | 同一条 query 跑 10 次至少复现 1 次问题 |
| 区分度 | frontier vs eval 差距 ≥ 10 分 | benchmark 能有效区分模型好坏 |

## 依赖

- **Python 3.10+**
- **Node 18+**（Platform CLI 用）
- **Platform CLI**：本仓库 `Platform/` 目录已内置，无需额外安装，直接 `node Platform/Platform.mjs` 使用
