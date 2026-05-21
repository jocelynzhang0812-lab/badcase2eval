-- Fuck Bench L1 SQL (English profanity only)
-- L1 = 英文脏话，后续 L2 可扩展中文脏话、vote_down 等信号
-- 主题：用户在对话中段爆粗口的 chat_id 召回
-- 输出：chat_id + 最小元数据（供下游 data-get_message.py 拉 trace）
-- 参数：${target_date} 目标分区日期（如 2026-04-12）
-- 详细流程见 references/data-insight-flow.md

WITH dirty_msgs AS (
  SELECT
    chat_id,
    user_message_id,
    group_index,
    user_message_create_time,
    scenario,
    vote_status
  FROM mart_kimi.dws_chat_group_base_di
  WHERE dt = '${target_date}'
    AND dt IS NOT NULL AND dt != 'None'
    AND group_index > 1                                  -- 非首句
    AND LOWER(user_content) RLIKE
        '(^|[^a-z])(fuck(ing|ed|er)?|fck|f\\*ck|wtf|stfu)([^a-z]|$)'
),
long_sessions AS (
  SELECT chat_id
  FROM mart_kimi.dws_chat_group_base_di
  WHERE dt = '${target_date}'
    AND dt IS NOT NULL AND dt != 'None'
  GROUP BY chat_id
  HAVING COUNT(*) >= 5
)
SELECT d.*
FROM dirty_msgs d
JOIN long_sessions s USING (chat_id)
LIMIT 2000;  -- 经验值：人工标注约 200 条/天，2000 条留一周缓冲；避免 OSS 导出超时
