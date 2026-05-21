# dws_chat_group_detail_day

## 别名
用户问答明细宽表, 会话明细宽表, 问答明细表, chat_log, 对话明细数据

## 描述
用户问答明细宽表，组装各种数据源的会话数据，每行数据代表一次问答（一问一答）。可根据各种ID（chat_id、user_id、ssid等）、场景标签（labels、intents等）捞取用户会话明细数据。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 每行代表一次问答（user_content + assistant_content）
- 主要数据源：C端用户对话、Finder对话等
- 典型场景：用户行为分析、对话质量分析、模型效果评估、场景标签分析

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_chat_group_detail_day | - | - | ODPS 项目 mart_kimi |
| hologres | dws_chat_group_detail_day | default | ext_mc_holo | Hologres 加速表，与 ODPS 表名一致 |

## 字段别名

| 字段名称 | 别名 |
|---------|------|
| user_content | 用户问题 |
| assistant_content | 模型回答 |
| segment_thumb_status | 点赞状态 |
| model | 使用模型 |
| kimiplus_id | KimiPlusID |
| kimiplus_name | KimiPlus名称, AI_Platform+ 名称, kimiplus名称 |
| first_scenario | 首次会话场景 |
| tokens | Token数量 |
| question_tokens | 问题Token数 |
| search_tokens | 搜索Token数 |
| group_index | 当天对话轮次 |
| history_group_index | 历史对话轮次 |
| user_content_len | 问题长度 |
| assistant_content_len | 回答长度 |
| model_request_types | 请求类型列表 |
| model_request_langs | 请求语言列表 |
| request_model_ids | 请求模型列表 |
| finish_reasons | 结束原因列表 |
| inference_clusters | 推理集群列表 |
| skus | SKU列表 |
| initial_latency | 准备耗时 |
| total_time_cost | 总耗时 |
| prompt_tokens | 输入Token数 |
| completion_tokens | 输出Token数 |
| cached_tokens | 缓存Token数 |
| mooncake_boosted_tokens | Mooncake增强Token数 |
| total_gpu_time_cost | 总GPU耗时 |
| prefill_gpu_time_cost | 预填充GPU耗时 |
| generation_gpu_time_cost | 生成GPU耗时 |
| input_image_count | 输入图片数 |
| inference_models | 推理模型列表 |
| prefill_cost_in_rmb | 预填充成本 |
| generation_cost_in_rmb | 生成成本 |
| query_filter_accepted_list | 输入审核通过列表 |
| query_filter_reasons | 输入审核拒绝原因 |
| query_filter_refs | 输入审核关键词, query审核关键词 |
| response_filter_accepted_list | 回复审核通过列表 |
| response_filter_reasons | 回复审核拒绝原因 |
| response_filter_refs | 回复审核关键词, response审核关键词, resp审核关键词 |
| query_filter_reason_2 | 输入拦截原因L2 |
| response_filter_reason_2 | 回复拦截原因L2 |
| file_object_keys | 文件对象Keys |
| user_finder_actions | 用户Finder行为 |
| assistant_finder_actions | 模型Finder行为 |
| finder_platform | Finder平台 |
| prefill_cost | 预填充成本 |
| generation_cost | 生成成本 |
| charge_query_content_filter_num | 计费输入审核次数 |
| charge_response_content_filter_num | 计费回复审核次数 |
| tr_code | 广告追踪码 |
| main_model_request_langs | 主模型请求语言 |
| main_finish_reasons | 主模型结束原因 |
| main_inference_clusters | 主模型推理集群 |
| main_inference_models | 主模型推理模型 |
| user_space_id | 用户空间ID |
| depth | 会话深度 |
| tool_node_name_list | 工具节点列表, tool_nodes, 工具列表 |
| kfc_consumed_credits | KFC消耗额度 |
| is_first_message | 是否首条消息 |
| sandbox_file_types | 产出物类型列表, kimi_ref产出物类型 |
| workflows | Workflow列表, workflow集合, 工作流列表 |
| workflow_status | Workflow状态 |
| request_tool_types | 请求工具类型 |
| file_types | 文件类型列表 |
| last_trace_id | 最后TraceID |

## 计算字段
| 字段名称 | 别名                         | 表达式                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|---------|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|会话入口| 入口                         | case when  (array_contains(request_model_ids,'OpenAI-compatible-x35-text-free-basic-chat')) then 'k2d5'when (array_contains(request_model_ids,'OpenAI-compatible-x35-think-free-turbo-chat') or array_contains(request_model_ids,'OpenAI-compatible-x35-think-kpro-turbo-chat')) then 'k2d5thinking'when model = 'SCENARIO_OK_COMPUTER' and array_contains(request_tool_types,'TOOL_TYPE_PARALLEL_AGENT') then 'k2d5agent集群'when model = 'SCENARIO_OK_COMPUTER' and COALESCE(kimiplus_id,'') = '' then 'k2d5agent'when model = 'SCENARIO_OK_COMPUTER' and COALESCE(kimiplus_id,'') = 'websites' then '网站'when model = 'SCENARIO_OK_COMPUTER' and COALESCE(kimiplus_id,'') = 'docs' then '文档'when model = 'SCENARIO_SLIDES' and COALESCE(kimiplus_id,'') = 'slides' then 'PPT'when model = 'SCENARIO_OK_COMPUTER' and COALESCE(kimiplus_id,'') = 'sheets' then '表格'when model = 'SCENARIO_DEEP_RESEARCH' then '深度研究' else '其他' end |
|Internal_Tool 对话数| Internal_Tool chat数                  | count(distinct case when `会话入口` in ('k2d5agent集群', 'k2d5agent', '网站', '文档', 'PPT', '表格') then chat_id end)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
|点踩状态| 点踩状态                       | CASE WHEN segment_thumb_status = '1' THEN '点赞'WHEN segment_thumb_status = '2' THEN '点踩'ELSE '无'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
|是否携带文件| 带文件                        | CASE  WHEN INSTR(labels, 'has_file') > 0 or ("url_file_refs" is not null  and "user_file_refs" != '') THEN '是'  ELSE '否'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
|是否携带图片| 带图片                        | CASE     WHEN INSTR(labels, 'has_image') > 0 THEN '是'    ELSE '否'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
|是否生图对话| 生图, 生图对话                   | CASE     WHEN gen_image_num > 0 THEN '是'    ELSE '否'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|是否kimiv| kimiv                      | CASE     WHEN INSTR(labels, 'user_kimiv') > 0 THEN '是'    ELSE '否'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
|对话轮次区间| 对话轮次区间                     | case when group_index = 1 then '首轮'when group_index>1 and group_index<=5 then '第[2-5]轮'when group_index>5 and group_index<=10 then '第[6-10]轮'when group_index>10 and group_index<=20 then '第[11-20]轮'when group_index>20 and group_index<=100 then '第[21-100]轮'ELSE '100轮以上'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
|是否为第一条message| 首条 Message                 | CASE  WHEN is_first_message = 1 THEN '是'  ELSE '否'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
|新老用户| 老用户, 新用户                   | CASE    WHEN user_id LIKE 'anon%' THEN '匿名用户'    WHEN DATE(user_created_at) = DATE(dt) THEN '注册新用户'    ELSE '注册老用户'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
|是否有反馈内容| 有反馈, 无反馈                   | CASE     WHEN last_feedback_content IS NOT NULL AND last_feedback_content != '' THEN '是'    ELSE '否'END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|tool_node个数| tool个数                     | SIZE(tool_node_name_list)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|是否有沙盒产出物| 有沙盒产出物, 无沙盒产出物             | case when SIZE(sandbox_shell_list_file_types)>0 then '有' else '无' end                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
|workflow是否报错| workflow报错, workflow正常     | case when SIZE(workflow_status) > 0 and workflow_status[0] <> '{}' then '有' else '无' end                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
|是否有kimi_ref产出物| 有kimi_ref产出物, 无kimi_ref产出物 | case when SIZE(sandbox_file_types) > 0 then '有' else '无' end                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|query是否被风控| query被风控, query没有被风控       | CASE     WHEN ARRAY_CONTAINS(query_filter_accepted_list, '0') THEN '是'     ELSE '否' END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|resp是否被风控| resp被风控, resp没有被风控         | CASE     WHEN ARRAY_CONTAINS(response_filter_accepted_list, '0') THEN '是'     ELSE '否' END                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

## 常用字段组合
**基础信息**
```sql
dt as `日期`,
chat_id,
history_group_index as `chat历史轮次`,
group_index as `chat单天轮次`,
user_segment_id as `用户segment_id`,
assistant_segment_id as `模型segment_id`,
segment_platform as `对话平台`,
user_id,
ssid,
user_region as `用户region`,
user_country_code as `用户注册国家代码`,
CASE WHEN user_id LIKE 'anon%' THEN '匿名用户' WHEN CAST(user_created_at AS DATE) = CAST(dt AS DATE) THEN '注册新用户' ELSE '注册老用户' END as `新老用户`
created_at as `对话创建时间`,
locale as `语言环境`,
intents as `搜索意图`,
labels,
user_content as `用户query`,
CASE WHEN ARRAY_CONTAINS(query_filter_accepted_list, '0') THEN '是' ELSE '否' END as `query是否被风控`,
query_filter_refs as `query审核关键词`,
assistant_content as `模型resp`,
CASE WHEN ARRAY_CONTAINS(response_filter_accepted_list, '0') THEN '是' ELSE '否' END as `resp是否被风控`,
response_filter_refs as `resp审核关键词`,
CASE WHEN segment_thumb_status = '1' THEN '点赞' WHEN segment_thumb_status = '2' THEN '点踩' ELSE '无' END as `点踩状态`,
last_feedback_content as `最新反馈内容`,
user_file_refs as `用户文件`,
file_names as `用户文件名`,
assistant_file_refs as `模型文件`,
model as `模型`,
inference_models as `推理模型`,
main_model_request_langs as `主请求语言`,
main_finish_reasons as `主请求finish_reasons`,
main_inference_clusters as `主请求推理集群`,
main_inference_models as `主请求推理模型`,
main_image_in as `主请求image_in`,
main_inference_node_names,
main_model_real_provider_ids as `主请求provider_id`,
model_request_id as `模型请求id`,
total_tokens * 1.0 as `total_tokens`,
prompt_tokens * 1.0 as `prompt_tokens`
completion_tokens * 1.0 as `completion_tokens`
mooncake_boosted_tokens, 
small_model_tag_1 as `小模型一级tag`,
small_model_tag_2 as `小模型二级tag`,
small_model_tag_3 as `小模型三级tag`,
user_created_at as `用户注册时间`,
ab_versions,
ip,
membership_level as `会员等级`,
membership_status as `会员订阅状态`,
trace_id,
file_content_types as `用户文件类型`,
first_scenario as `会话首次场景`,
tool_node_name_list,
request_model_ids as `请求模型list`,
last_feedback_tags as `最新反馈tags`,
db_version as `后端库表版本`,
is_open_thinking_option as `是否开启长思考选项`,
is_tool_type_search as  `是否为开启联网模式`,
CASE WHEN is_first_message = 1 THEN '是' ELSE '否' END as `是否为第一条message`,
file_sizes,
COALESCE(SIZE(file_names), 0) as `用户文件数量`,
workflows,
CASE WHEN SIZE(workflow_status) > 0 AND workflow_status[0] <> '{}' THEN '有' ELSE '无' END as `workflow是否报错`
workflow_status,
CASE WHEN ARRAY_CONTAINS(request_model_ids, 'OpenAI-compatible-x35-text-free-basic-chat') THEN 'k2d5' WHEN ARRAY_CONTAINS(request_model_ids, 'OpenAI-compatible-x35-think-free-turbo-chat') OR ARRAY_CONTAINS(request_model_ids, 'OpenAI-compatible-x35-think-kpro-turbo-chat') THEN 'k2d5thinking' WHEN model = 'SCENARIO_OK_COMPUTER' AND ARRAY_CONTAINS(request_tool_types, 'TOOL_TYPE_PARALLEL_AGENT') THEN 'k2d5agent集群' WHEN model = 'SCENARIO_OK_COMPUTER' AND COALESCE(kimiplus_id, '') = '' THEN 'k2d5agent' WHEN model = 'SCENARIO_OK_COMPUTER' AND COALESCE(kimiplus_id, '') = 'websites' THEN '网站' WHEN model = 'SCENARIO_OK_COMPUTER' AND COALESCE(kimiplus_id, '') = 'docs' THEN '文档' WHEN model = 'SCENARIO_SLIDES' AND COALESCE(kimiplus_id, '') = 'slides' THEN 'PPT' WHEN model = 'SCENARIO_OK_COMPUTER' AND COALESCE(kimiplus_id, '') = 'sheets' THEN '表格' WHEN model = 'SCENARIO_DEEP_RESEARCH' THEN '深度研究' ELSE '其他' END as `会话入口`,
CASE WHEN SIZE(sandbox_shell_list_file_types) > 0 THEN '有' ELSE '无' END as `是否有沙盒产出物`,
sandbox_shell_list_file_types as `沙盒产出物全部`,
CASE WHEN SIZE(sandbox_file_types) > 0 THEN '有' ELSE '无' END as `是否有kimi_ref产出物`,
sandbox_file_types as `kimi_ref产出物类型`,
CASE WHEN gen_image_num > 0 OR actions LIKE '%gen_image_shumei_risk%' THEN '生图tool' WHEN group_id = 'system' THEN '系统请求' WHEN labels LIKE '%user_kimiv%' THEN 'kimiv' WHEN labels LIKE '%kimi_search%' THEN '普通搜索' WHEN labels LIKE '%kimi_search_rag%' THEN 'rag搜索' WHEN labels LIKE '%solve_problem_image%' THEN '拍照解题（含task bar）' WHEN labels LIKE '%user_writing%' THEN 'app端task bar写作' WHEN labels LIKE '%user_translation%' THEN 'app端task bar翻译' WHEN labels LIKE '%show_case%' THEN '首页case创建' WHEN labels LIKE '%user_math%' THEN 'k1-math' WHEN labels LIKE '%audio_rtc%' THEN '语音通话' WHEN labels LIKE '%deep_research_clarify%' OR labels LIKE '%deep_research%' THEN 'Researcher' WHEN kimiplus_id = 'cvvm7bkheutnihqi2100' THEN 'PPT' WHEN model = 'SCENARIO_OK_COMPUTER' THEN 'Internal_Tool' ELSE '其他' END as `产品入口`
```
**ID映射关系**
```sql
chat_id, user_segment_id, assistant_segment_id, trace_id, small_model_tag_3 as `小模型三级tag`, CASE WHEN is_first_message = 1 THEN '是' ELSE '否' END as `是否为第一条message`
```
## 查询示例（fewshot，帮助大模型理解复杂需求）

### 随机采样查询

> **hash 采样原理**：`ABS(HASH(CONCAT(model_request_id, CAST(dt AS STRING)))) % 100000` 生成 0~99999 的均匀分布哈希值。
> - 全表单天数据量约千万级，`hash <= 5` 约采样 0.006%（几千条）
> - **子集数据**（如经过 WHERE 过滤后）行数较少时，需根据实际数据量调整阈值
> - 公式：`阈值 ≈ 目标行数 / 总行数 × 100000`
>
> ️ **必须先确认用户需要的数据量级**，再计算合适的 hash 阈值。

```sql
-- 全表采样（单天千万级 → ~几千条）
SELECT * FROM dws_chat_group_detail_day
WHERE dt = '2026-03-01'
  AND ABS(HASH(CONCAT(model_request_id, CAST(dt AS STRING)))) % 100000 <= 5
LIMIT 1000

-- 子集采样（如 vibe coding 7天 ~20万条 → ~1000条，阈值 ≈ 1000/200000*100000 ≈ 510）
-- 时间段完全在 20260127 之后，使用模式A（严格）
SELECT * FROM mart_kimi.dws_chat_group_detail_day
WHERE dt BETWEEN '2026-01-27' AND '2026-02-02'
  AND ARRAY_CONTAINS(workflows, 'WORKFLOW_VIBE_CODING_WEBSITES')
  AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')
  AND ABS(HASH(CONCAT(model_request_id, CAST(dt AS STRING)))) % 100000 <= 510
LIMIT 1000
```

### Vibe Coding 数据查询（重点）

> **背景**：2026-01-27 AI_Platform K2.5 上线后，vibe coding 对话的 `workflows` 字段才包含 `WORKFLOW_VIBE_CODING_WEBSITES`。上线前只能通过 `tool_node_name_list` 包含 `mshtools-deploy_website` 来筛选。
>
> `workflows` 和 `tool_node_name_list` 是 `array<string>` 类型，需使用 `ARRAY_CONTAINS` 函数。

> ** 筛选模式自动选择**（根据时间段自动决定，无需询问用户，但必须在展示 SQL 时明确告知用户当前使用的筛选模式及原因）：
> - **数据时间段完全在 20260127 之后**：默认使用**模式A（严格）**  同时筛选 `ARRAY_CONTAINS(workflows, 'WORKFLOW_VIBE_CODING_WEBSITES') AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')`
> - **数据时间段在 20260127 之前**：自动切换为**模式B（宽松）**  仅筛选 `ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')`
> - **数据时间段跨越 20260127**：自动切换为模式B（宽松），确保前后数据口径一致
>
> ** 其他默认配置**：
> - **字段组合**：基础信息（与 insight 平台对齐）
> - **可视化链接**：优先使用 `vibe-coding-viewer` skill 生成链接，**直接传入 OSS 路径即可，无需下载到本地**（`https://viewer.internal.ai.com/?path={url_encoded_path}`）
> - 询问用户时展示为推荐选项，让用户确认即可
>
> ** 首轮/非首轮区分**：
> 当用户要求区分首轮和非首轮对话时，使用 `is_first_message` 字段（`1`=首轮，`0`=非首轮）：
> - **筛选首轮**：`AND is_first_message = 1`
> - **筛选非首轮**：`AND is_first_message = 0`
> - **不筛选但展示**：基础信息字段组合已包含 `CASE WHEN is_first_message = 1 THEN '是' ELSE '否' END as 是否为第一条message`

**筛选模式说明**：

| 模式 | 条件 | 适用场景 | 默认使用时机 |
|------|------|----------|------------|
| **模式A**（严格，默认） | `ARRAY_CONTAINS(workflows, 'WORKFLOW_VIBE_CODING_WEBSITES') AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')` | K2.5 上线后，双条件精确匹配 | 数据时间段完全在 **20260127 之后** |
| **模式B**（宽松） | `ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')` | 跨时间段对比，不依赖 workflow 标记 | 数据时间段在 **20260127 之前**，或**跨越** 20260127 |

```sql
-- 模式A（严格，默认）：workflow + tool_node 双条件  数据时间段完全在 20260127 之后时使用
SELECT *
FROM mart_kimi.dws_chat_group_detail_day
WHERE dt = '2026-02-28'
  AND ARRAY_CONTAINS(workflows, 'WORKFLOW_VIBE_CODING_WEBSITES')
  AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')
LIMIT 1000

-- 模式B（宽松）：仅 tool_node 筛选  数据时间段在 20260127 之前，或跨越 20260127 时使用
SELECT *
FROM mart_kimi.dws_chat_group_detail_day
WHERE dt = '2026-01-20'
  AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')
LIMIT 1000
```

### Workflow 枚举值

> 以下为 `workflows` 字段（`array<string>`）中的所有已知枚举值，按数据量排序。

| Workflow 名称 | 说明 | 量级参考（单天） |
|--------------|------|----------------|
| `WORKFLOW_K2D5` | K2.5 模型工作流 | ~1100万 |
| `WORKFLOW_OSS_COMPLETION` | OSS 补全工作流 | ~330万 |
| `WORKFLOW_K2` | K2 模型工作流 | ~19万 |
| `WORKFLOW_K2_THINKING` | K2 长思考工作流 | ~14万 |
| `WORKFLOW_SLIDES` | PPT/幻灯片生成工作流 | ~11万 |
| `WORKFLOW_PROBLEM_SOLVE` | 拍照解题工作流 | ~7.5万 |
| `WORKFLOW_OK_COMPUTER` | Internal_Tool（OK Computer）Agent 工作流 | ~6.4万 |
| `WORKFLOW_COMPACT_MEMORY` | 记忆压缩工作流 | ~6万 |
| `WORKFLOW_DEEP_RESEARCH` | 深度研究工作流 | ~1.4万 |
| `WORKFLOW_VIBE_CODING_WEBSITES` | Vibe Coding 网站生成工作流（20260127 K2.5 上线后才有） | ~9千 |
| `WORKFLOW_KIMI_CHAT` | AI_Platform Chat 工作流 | ~8千 |
| `WORKFLOW_AI_OFFICE_DOCS` | AI 办公 - 文档工作流 | ~8千 |
| `WORKFLOW_AI_OFFICE_SHEETS` | AI 办公 - 表格工作流 | ~2千 |
| `WORKFLOW_KIMIPLUS` | KimiPlus 自定义 Bot 工作流 | ~2千 |

### 常见 Tool Node 名称

| Tool Node 名称 | 说明 |
|---------------|------|
| `mshtools-deploy_website` | 部署网站工具 |
| `mshtools-read_file` | 读取文件工具 |
| `mshtools-web_search` | 网页搜索工具 |
