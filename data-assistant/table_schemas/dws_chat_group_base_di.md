# dws_chat_group_base_di

## 别名
会话明细宽表, 会话明细宽表, 用户问答明细宽表, 问答明细表, chat_log, 对话明细数据, 会话数据

## 描述
每行数据代表一次问答（一问一答），可根据各种 ID（chat_id、user_id、ssid 等）、场景标签（labels、intents 等）捞取用户会话明细数据。

- 离线表，数据 T+1 产出
- 按天分区（dt），格式：yyyy-MM-dd
- 每行代表一次问答（user_content + assistant_content）
- 主要数据源：C端用户对话、Finder 对话等
- 典型场景：用户行为分析、对话质量分析、模型效果评估、场景标签分析

## 数据源配置

| 数据源 | 表名 | Schema | Database | 说明 |
|--------|------|--------|----------|------|
| odps | dws_chat_group_base_di | - | - | ODPS 项目 mart_kimi |
| hologres | dws_chat_group_base_di | default | ext_mc_holo | Hologres 默认 schema |

## 字段别名

| 字段名称 | 别名/中文名                              |
|---------|-------------------------------------|
| dt | 日期                                  |
| chat_id | 会话ID                                |
| user_id | 用户ID                                |
| user_message_id | 用户messageID, 用户消息ID                 |
| assistant_message_id | 模型messageID, 模型消息ID, 助手messageID    |
| group_index | 消息轮次, 对话轮次                          |
| user_content | 用户消息内容, 用户query, 用户问题               |
| assistant_content | 模型回复内容, 模型resp, 助手回复内容              |
| user_depth | 用户消息深度                              |
| assistant_depth | 模型消息深度, 助手消息深度                      |
| scenario | 场景                                  |
| platform | 对话平台, 平台                            |
| kimiplus_id | KimiPlus ID, KimiPlusID             |
| model_type | 会话场景，                               |
| request_model_ids | 模型名称列表, 请求模型列表                      |
| model_provider_ids | 模型提供商列表                             |
| assistant_message_create_time | 模型message创建时间, 模型消息创建时间             |
| user_message_create_time | 用户message创建时间, 用户消息创建时间             |
| is_first_message | 是否会话首条消息, 是否首条消息, 首条消息              |
| chat_first_scenario | 会话首条消息场景, 首条场景                      |
| locale | 语言环境                                |
| user_message_status | 用户message状态, 用户消息状态                 |
| assistant_message_status | 模型message状态, 助手消息状态, 模型消息状态         |
| is_open_thinking_option | 是否开启长思考, 长思考开关                      |
| is_tool_type_search | 是否开启联网, 联网模式, 联网开关                  |
| membership_level | 会员等级                                |
| membership_status | 会员状态, 会员订阅状态                        |
| abstract_user_country_name | 用户国家                                |
| abstract_user_country_cn_short | 用户国家(中文), 用户国家中文                    |
| ssid | SSID                                |
| user_file_content_types | 用户文件类型                              |
| user_file_urls | 用户文件下载链接, 用户文件URL                   |
| kimi_ref_file_types | KimiRef文件类型, kimi_ref产出物类型          |
| assistant_file_types | 模型产出物文件类型, 沙盒产出物类型                  |
| assistant_file_urls | 模型产出物文件URL, 模型产出物下载链接               |
| inference_models | 推理模型                                |
| inference_cluster | 推理集群                                |
| main_inference_models | 主模型请求inference_models, 主推理模型        |
| main_model_real_provider_ids | 主模型请求真实提供商ID, 主模型提供商                |
| main_inference_node_names | 主模型请求inference_node_names           |
| request_tool_types | 用户请求tool, 请求工具类型                    |
| prompt_tokens | 提示词消耗tokens, 输入Token数               |
| completion_tokens | 模型消耗tokens, 输出Token数                |
| total_tokens | 总消耗tokens, Total Tokens             |
| cached_tokens | 缓存tokens, 缓存Token数                  |
| mooncake_boosted_tokens | mooncake增强的tokens, Mooncake增强Token数 |
| initial_latency | 初始延迟(ms), 准备耗时                      |
| total_time_cost | 总耗时(ms), 总时间消耗                      |
| total_gpu_time_cost | 总GPU耗时(ms), 总GPU时间                  |
| prefill_gpu_time_cost | prefill阶段GPU耗时(ms), 预填充GPU耗时        |
| generation_gpu_time_cost | generation阶段GPU耗时(ms), 生成GPU耗时      |
| prefill_batch_size | prefill阶段批次大小, 预填充批次                |
| input_image_count | 输入图片数量                              |
| input_image_parts_total | 输入图片切分数量                            |
| input_image_fetch_duration | 图片获取耗时(ms)                          |
| main_image_in | 主模型请求image_in, 主请求图片输入              |
| workflows | workflow集合, 工作流列表                   |
| workflow_status | workflow状态集合, 工作流状态                 |
| tool_node_name_list | 使用的tool集合, 工具节点列表, tool_nodes       |
| trace_id | Trace ID                            |
| all_trace_ids | 所有Trace ID                          |
| user_first_event_time | 用户首次事件时间                            |
| user_created_time | 用户创建时间, 用户注册时间                      |
| user_updated_time | 用户更新时间                              |
| user_message_update_time | 用户message更新时间, 用户消息更新时间             |
| assistant_message_update_time | 模型message更新时间, 助手消息更新时间             |
| user_message_delete_time | 用户message删除时间, 用户消息删除时间             |
| model_thinking_content | 模型思考过程, 思考内容                        |
| vote_status | 点赞状态, 点踩状态                          |
| dr_stage | deepresearch阶段, DR阶段                |
| abstract_user_id | 绝对用户ID                              |
| abstract_user_region | 用户地区, 用户区域                          |
| abstract_user_country_code | 用户国家编码, 国家代码                        |
| user_last_ip | 用户最后登录IP, 用户IP                      |
| tr_code | 广告追踪code, 广告追踪码                     |
| user_device_id | 用户设备ID, 设备ID                        |
| user_device_platform | 用户设备平台, 设备平台                        |
| user_device_active | 设备是否激活                              |
| user_device_app_version | 用户App版本, App版本                      |
| os_name | 发消息事件os, 操作系统                       |
| finder_platform | 发消息事件上报平台, 上报平台                     |
| user_device_web_id | 用户Web ID, Web ID                    |
| user_device_push_provider | 推送提供商                               |
| user_file_ids | 用户文件ID                              |
| user_file_names | 用户文件名, 用户文件名称                       |
| user_file_sizes | 用户文件大小                              |
| user_file_object_keys | 用户文件Object Key                      |
| user_file_infos | 用户文件元信息, 用户文件信息                     |
| kimi_ref_file_uris | KimiRef文件URL, kimi_ref文件链接          |
| assistant_file_names | 模型产出物文件名, 产出物文件名                    |
| model | 模型(仅v1存在)                           |
| model_tag_1 | 模型一级tag, 小模型一级tag                   |
| main_inference_clusters | 主模型请求inference_clusters, 主推理集群      |
| search_intents | 搜索意图                                |
| model_request_types | 模型请求类型, 请求类型列表                      |
| finish_reasons | 完成原因, Finish Reasons                |
| model_request_num | 模型请求数, 请求数量                         |
| inference_image_tags | 推理镜像标签                              |
| user_err_type | 用户message错误类型, 用户错误类型               |
| user_err_detail | 用户message错误详情, 用户错误详情               |
| assistant_err_type | 模型message错误类型, 助手错误类型               |
| assistant_err_detail | 模型message错误详情, 助手错误详情               |
| assistant_feedback_tags | 用户对模型回答的反馈标签, 反馈标签                  |
| assistant_feedback_content | 用户对模型回答的反馈内容, 反馈内容                  |
| msh_feedback_submit_reason | 反馈原因, 反馈提交原因                        |
| labels | message标签, 消息标签                     |
| organization_id | 组织ID, 组织标识                          |
| skus | SKU列表                               |
| ab_versions | AB实验版本, AB版本                        |
| db_version | 后端库表版本, 库表版本                        |
| main_finish_reasons | 主模型请求finish_reasons, 主完成原因          |
| user_content_filter_num | 用户送审内容数量, 用户审核数量                    |
| assistant_content_filter_num | 模型送审内容数量, 模型审核数量                    |
| charge_user_content_filter_num | 用户送审内容未被cache的审核数量, 用户计费审核数         |
| charge_assistant_content_filter_num | 模型送审内容未被cache的审核数量, 模型计费审核数         |
| user_filter_accepted_list | 用户送审内容触发风控, 用户风控状态                  |
| assistant_filter_accepted_list | 模型送审内容触发风控, 模型风控状态                  |
| user_filter_source_list | 用户送审供应商名称, 用户审核供应商                  |
| assistant_filter_source_list | 模型送审供应商名称, 模型审核供应商                  |
| user_filter_reasons | 用户送审内容被风控的原因, 用户风控原因                |
| assistant_filter_reasons | 模型送审内容被风控的原因, 模型风控原因                |
| user_first_reasons | 用户送审内容第一个被审核的原因, 用户首要风控原因           |
| assistant_first_reasons | 模型送审内容第一个被审核的原因, 模型首要风控原因           |
| user_filter_content_types | 用户送审内容的类型, 用户审核内容类型                 |
| assistant_filter_content_types | 模型送审内容的类型, 模型审核内容类型                 |
| user_filter_refs | 用户送审触发风控的内容, 用户风控内容                 |
| assistant_filter_refs | 模型送审触发风控的内容, 模型风控内容, resp审核关键词      |
| user_filter_time_cost | 用户送审内容审核总时长(ms), 用户审核耗时             |
| assistant_filter_time_cost | 模型送审内容审核总时长(ms), 模型审核耗时             |

## 计算字段


## 常用字段组合

**基础信息**
```sql
dt as `日期`,
chat_id as `会话ID`,
group_by_id as `问答组ID`,
user_message_id as `用户消息ID`,
assistant_message_id as `模型消息ID`,
trace_id as `Trace ID`,
concat_ws(',', all_trace_ids) as `所有Trace IDs`,
last_trace_id as `末次Trace ID`,
user_id as `用户ID`,
scenario as `场景`,
platform as `对话平台`,
user_message_status as `用户消息状态`,
assistant_message_status as `模型消息状态`,
user_depth as `用户消息深度`,
assistant_depth as `模型消息深度`,
group_index as `消息轮次`,
user_content as `用户消息内容`,
assistant_content as `模型回复内容`,
concat_ws(',', labels) as `消息标签`,
vote_status as `点赞状态`,
chat_first_scenario as `首条场景`,
is_open_thinking_option as `是否开启长思考`,
is_tool_type_search as `是否开启联网`,
dr_stage as `DR阶段`,
concat_ws(',', user_file_ids) as `用户文件IDs`,
concat_ws(',', user_file_content_types) as `用户文件类型`,
concat_ws(',', user_file_names) as `用户文件名`,
concat_ws(',', user_file_sizes) as `用户文件大小`,
concat_ws(',', user_file_object_keys) as `用户文件Object Keys`,
concat_ws(',', user_file_infos) as `用户文件信息`,
concat_ws(',', user_file_urls) as `用户文件下载链接`,
concat_ws(',', kimi_ref_file_uris) as `KimiRef文件URIs`,
concat_ws(',', kimi_ref_file_types) as `KimiRef文件类型`,
concat_ws(',', assistant_file_names) as `模型产出物文件名`,
concat_ws(',', assistant_file_types) as `模型产出物类型`,
concat_ws(',', assistant_file_urls) as `模型产出物下载链接`,
user_err_type as `用户错误类型`,
assistant_err_type as `模型错误类型`,
user_err_detail as `用户错误详情`,
assistant_err_detail as `模型错误详情`,
model_thinking_content as `模型思考过程`,
concat_ws(',', request_tool_types) as `请求工具类型`,
user_message_create_time as `用户消息创建时间`,
assistant_message_create_time as `模型消息创建时间`,
user_message_update_time as `用户消息更新时间`,
assistant_message_update_time as `模型消息更新时间`,
user_message_delete_time as `用户消息删除时间`,
db_version as `库表版本`,
env_type as `环境类型`,
kimiplus_id as `KimiPlus ID`,
concat_ws(',', assistant_feedback_tags) as `反馈标签`,
assistant_feedback_content as `反馈内容`,
model as `模型`,
user_device_id as `设备ID`,
user_device_active as `设备是否激活`,
user_device_platform as `设备平台`,
user_device_push_provider as `推送提供商`,
user_device_app_version as `App版本`,
user_device_web_id as `Web ID`,
abstract_user_id as `绝对用户ID`,
user_last_ip as `用户最后IP`,
user_created_time as `用户创建时间`,
user_updated_time as `用户更新时间`,
abstract_user_region as `用户地区`,
abstract_user_country_code as `用户国家编码`,
abstract_user_country_name as `用户国家`,
abstract_user_country_cn_short as `用户国家中文`,
membership_level as `会员等级`,
membership_status as `会员状态`,
concat_ws(',', CAST(ab_versions AS ARRAY<STRING>)) as `AB实验版本`,
ssid as `SSID`,
concat_ws(',', user_finder_actions) as `用户Finder行为`,
concat_ws(',', assistant_finder_actions) as `模型Finder行为`,
finder_platform as `Finder平台`,
os_name as `操作系统`,
concat_ws(',', msh_feedback_submit_reason) as `反馈原因`,
user_first_event_time as `用户首次事件时间`,
locale as `语言环境`,
is_first_message as `是否首条消息`,
tr_code as `广告追踪码`,
concat_ws(',', search_intents) as `搜索意图`,
concat_ws(',', user_filter_accepted_list) as `用户风控状态`,
concat_ws(',', assistant_filter_accepted_list) as `模型风控状态`,
concat_ws(',', user_filter_source_list) as `用户审核供应商`,
concat_ws(',', assistant_filter_source_list) as `模型审核供应商`,
concat_ws(',', user_filter_reasons) as `用户风控原因`,
concat_ws(',', assistant_filter_reasons) as `模型风控原因`,
user_filter_time_cost as `用户审核耗时`,
assistant_filter_time_cost as `模型审核耗时`,
concat_ws(',', user_filter_content_types) as `用户审核内容类型`,
concat_ws(',', assistant_filter_content_types) as `模型审核内容类型`,
concat_ws(',', user_filter_refs) as `用户风控内容`,
concat_ws(',', assistant_filter_refs) as `模型风控内容`,
user_content_filter_num as `用户审核数量`,
assistant_content_filter_num as `模型审核数量`,
concat_ws(',', user_first_reasons) as `用户首要风控原因`,
concat_ws(',', assistant_first_reasons) as `模型首要风控原因`,
charge_user_content_filter_num as `用户计费审核数`,
charge_assistant_content_filter_num as `模型计费审核数`,
organization_id as `组织ID`,
concat_ws(',', request_group_id) as `请求组ID`,
model_request_num as `模型请求数`,
concat_ws(',', model_request_types) as `模型请求类型`,
concat_ws(',', request_model_ids) as `请求模型列表`,
concat_ws(',', model_provider_ids) as `模型提供商列表`,
concat_ws(',', finish_reasons) as `完成原因`,
concat_ws(',', inference_models) as `推理模型`,
concat_ws(',', inference_cluster) as `推理集群`,
concat_ws(',', inference_image_tags) as `推理镜像标签`,
concat_ws(',', skus) as `SKU列表`,
initial_latency as `初始延迟`,
total_time_cost as `总耗时`,
total_gpu_time_cost as `总GPU耗时`,
prefill_gpu_time_cost as `预填充GPU耗时`,
generation_gpu_time_cost as `生成GPU耗时`,
prefill_batch_size as `预填充批次`,
input_image_count as `输入图片数量`,
input_image_parts_total as `输入图片切分数量`,
input_image_fetch_duration as `图片获取耗时`,
prompt_tokens as `提示词消耗tokens`,
completion_tokens as `模型消耗tokens`,
total_tokens as `总消耗tokens`,
cached_tokens as `缓存tokens`,
mooncake_boosted_tokens as `Mooncake增强tokens`,
prefill_cost as `预填充成本`,
generation_cost as `生成成本`,
total_cost as `总成本`,
concat_ws(',', main_finish_reasons) as `主完成原因`,
concat_ws(',', main_inference_clusters) as `主推理集群`,
concat_ws(',', main_inference_models) as `主推理模型`,
concat_ws(',', main_image_in) as `主请求图片输入`,
concat_ws(',', main_model_real_provider_ids) as `主模型提供商`,
concat_ws(',', main_inference_node_names) as `主推理节点`,
assistant_refs as `引用`,
chat_request as `请求配置`,
concat_ws(',', workflows) as `工作流列表`,
concat_ws(',', workflow_status) as `工作流状态`,
concat_ws(',', tool_node_name_list) as `工具节点列表`,
model_tag_1 as `模型一级tag`,
model_tag_2 as `模型二级tag`,
model_tag_3 as `模型三级tag`,
model_type as `模型类型`
```

**ID映射关系**
```sql
chat_id as `会话ID`,
user_id as `用户ID`,
user_message_id as `用户消息ID`,
assistant_message_id as `模型消息ID`,
trace_id as `Trace ID`,
CASE WHEN is_first_message = 1 THEN '是' ELSE '否' END as `是否为第一条message`
```

## 查询示例

### 随机采样查询

> **hash 采样原理**：`ABS(HASH(CONCAT(trace_id, CAST(dt AS STRING)))) % 100000` 生成 0~99999 的均匀分布哈希值。
> - 全表单天数据量约千万级，`hash <= 5` 约采样 0.006%（几千条）
> - **子集数据**（如经过 WHERE 过滤后）行数较少时，需根据实际数据量调整阈值
> - 公式：`阈值 ≈ 目标行数 / 总行数 × 100000`
> ️ **必须先确认用户需要的数据量级**，再计算合适的 hash 阈值。
> - **不要**使用 `WHERE RAND() < 0.01` 采样，性能差且容易出错。

```sql
-- 全表采样（单天千万级 → ~几千条）
SELECT * FROM dws_chat_group_base_di
WHERE dt = '2026-03-01'
  AND ABS(HASH(CONCAT(trace_id, CAST(dt AS STRING)))) % 100000 <= 5
LIMIT 1000

-- 子集采样（如 vibe coding 7天 ~20万条 → ~1000条，阈值 ≈ 1000/200000*100000 ≈ 510）
SELECT * FROM mart_kimi.dws_chat_group_base_di
WHERE dt BETWEEN '2026-01-27' AND '2026-02-02'
  AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')
  AND ABS(HASH(CONCAT(trace_id, CAST(dt AS STRING)))) % 100000 <= 510
LIMIT 1000
```

### Vibe Coding 数据查询（重点）

> **背景**：2026-01-27 AI_Platform K2.5 上线后，vibe coding 对话的 `workflows` 字段才包含 `WORKFLOW_VIBE_CODING_WEBSITES`。上线前只能通过 `tool_node_name_list` 包含 `mshtools-deploy_website` 来筛选。
>
> `workflows` 和 `tool_node_name_list` 是 `array<string>` 类型，需使用 `ARRAY_CONTAINS` 函数。
>
> ️ **存在多种筛选模式时，必须询问用户选择哪种**，不要自行决定。

> ** 默认推荐**（已确认）：
> - **筛选模式**：A（宽松） 仅 `tool_node_name_list` 包含 `mshtools-deploy_website`
> - **字段组合**：基础信息（与 insight 平台对齐）
> - **可视化链接**：优先使用 `vibe-coding-viewer` skill 生成链接（`https://viewer.internal.ai.com/?path={url_encoded_path}`）
> - 询问用户时展示为推荐选项，让用户确认即可
>
> ** 首轮/非首轮区分**：
> 当用户要求区分首轮和非首轮对话时，使用 `is_first_message` 字段（`1`=首轮，`0`=非首轮）：
> - **筛选首轮**：`AND is_first_message = 1`
> - **筛选非首轮**：`AND is_first_message = 0`
> - **不筛选但展示**：基础信息字段组合已包含 `CASE WHEN is_first_message = 1 THEN '是' ELSE '否' END as 是否为第一条message`

**筛选模式说明**：

| 模式 | 条件 | 适用场景 |
|------|------|----------|
| **模式A**（宽松） | `ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')` | 跨时间段对比，不依赖 workflow 标记 |
| **模式B**（严格） | `ARRAY_CONTAINS(workflows, 'WORKFLOW_VIBE_CODING_WEBSITES') AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')` | K2.5 上线后（20260127+），双条件精确匹配 |

```sql
-- 模式A：仅 tool_node 筛选（适用所有时间段）
SELECT *
FROM mart_kimi.dws_chat_group_base_di
WHERE dt = '2026-02-28'
  AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')
    LIMIT 1000

-- 模式B：workflow + tool_node 双条件（仅 20260127 之后有效）
SELECT *
FROM mart_kimi.dws_chat_group_base_di
WHERE dt = '2026-02-28'
  AND ARRAY_CONTAINS(workflows, 'WORKFLOW_VIBE_CODING_WEBSITES')
  AND ARRAY_CONTAINS(tool_node_name_list, 'mshtools-deploy_website')
    LIMIT 1000
```



## 枚举映射
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
