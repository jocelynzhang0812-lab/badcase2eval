#!/usr/bin/env python3
"""
bloom_generate.py  基于 Bloom 方法论自动生成评测场景

从一个行为描述出发，自动生成多样化的评测数据集（query + rubric），
可直接进入 eval-skill 现有的 Chatty / Platform 评测链路。

融合了 Anthropic Bloom 的三个核心能力：
1. Understanding + Ideation：自动理解行为 → 生成多样化场景
2. Judge 自评质量：过滤不真实、无效的测试用例
3. 动态多轮诱导（可选）：生成 evaluator prompt 用于多轮测试

用法:
    # 基础：生成 10 个搜索词质量的测试场景
    python scripts/bloom_generate.py \
        --behavior "搜索词质量差" \
        --description "模型在需要搜索时生成的搜索词不精确、过长、缺少时间限定、语言不匹配用户问题" \
        --num-scenarios 10 \
        --output dataset.jsonl

    # 带变异维度：每个场景生成 difficulty × language 的变体
    python scripts/bloom_generate.py \
        --behavior "引用缺失" \
        --description "模型回复中引用了搜索结果但没有标注来源角标" \
        --num-scenarios 5 \
        --variations difficulty,query_language,topic_domain \
        --output dataset.jsonl

    # 带质量自检：过滤不真实或无效的场景
    python scripts/bloom_generate.py \
        --behavior "搜索词质量差" \
        --description "..." \
        --num-scenarios 20 \
        --self-check \
        --output dataset.jsonl

    # 多轮诱导模式：生成 evaluator 追问策略
    python scripts/bloom_generate.py \
        --behavior "多轮搜索遗忘" \
        --description "模型在多轮对话中忘记之前已经搜索过的信息，重复搜索相同内容" \
        --num-scenarios 5 \
        --multi-turn 3 \
        --output dataset.jsonl

环境变量:
    OPENAI_API_KEY   API key（必需）
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

# ---------- 配置 ----------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ai_service_BASE_URL = "https://gateway.internal.ai.com/v1"
DEFAULT_MODEL = os.environ.get("BLOOM_MODEL", "gpt-5.4")

for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(k, None)

# ---------- Prompts（提取自 Bloom 核心思想，适配产品体验场景）----------

UNDERSTANDING_PROMPT = """你是一个产品体验评测专家。请深入分析以下模型行为问题，为后续自动生成评测场景做准备。

## 行为名称
{behavior_name}

## 行为描述
{behavior_description}

{examples_section}

请输出以下分析（用 XML 标签包裹）：

<behavior_understanding>
1. 这个行为的本质是什么？为什么会发生？
2. 这个行为在哪些场景下最容易出现？
3. 这个行为的严重程度如何分级？（轻微 / 中等 / 严重）
4. 什么样的 query 最容易触发这个行为？
5. 如何客观判断这个行为是否发生了？（可验证的标准）
</behavior_understanding>

<scientific_motivation>
为什么评测这个行为很重要？它对用户体验有什么影响？
</scientific_motivation>

<variation_dimensions>
列出 3-5 个可以变化的维度，用于生成多样化的测试场景。
格式：维度名称: 说明
例如：
- difficulty: 简单问题 vs 复杂问题
- query_language: 中文 vs 英文 vs 混合语言
- topic_domain: 新闻 vs 学术 vs 生活 vs 技术
</variation_dimensions>"""

IDEATION_PROMPT = """你是一个评测数据集构造专家。基于以下行为分析，生成 {num_scenarios} 个多样化的评测场景。

## 行为理解
{understanding}

## 科学动机
{motivation}

{variations_section}

## 要求

为每个场景生成：
1. **query**: 用户会输入的问题（真实、自然、不要刻意设计）
2. **rubric**: 评判标准（客观、可验证、只测一个行为）
3. **scenario**: 场景分类标签
4. **difficulty**: easy / medium / hard
{multi_turn_section}

## 输出格式（严格 JSON 数组）

```json
[
  {{
    "query": "用户问题",
    "rubric": "评判标准：1. xxx 2. xxx",
    "scenario": "场景标签",
    "difficulty": "medium"
    {multi_turn_fields}
  }}
]
```

## 重要原则（来自 Bloom 方法论）

1. **单一行为**：每条只测一个明确的行为，不要混合多个问题
2. **真实性**：场景必须是用户真实会遇到的，不要过于人造
3. **多样性**：覆盖不同维度的变体，避免场景雷同
4. **可验证**：rubric 必须是客观可判断的，不要含糊
5. **难度梯度**：包含 easy(20%) / medium(50%) / hard(30%) 的分布

请直接输出 JSON 数组，不要加其他文字。"""

SELF_CHECK_PROMPT = """你是评测质量审核专家。请逐条检查以下评测场景，标记有问题的条目。

## 目标行为
{behavior_name}: {behavior_description}

## 待检查的场景
{scenarios_json}

对每条场景，评估以下质量维度（参考 Bloom 的 judgment 质量维度）：

1. **unrealism** (1-10): 场景是否过于人造/不真实？（1=非常真实，10=完全人造）
2. **evaluation_invalidity** (1-10): 评判标准是否真的能测出目标行为？（1=完全有效，10=完全无效）
3. **ambiguity** (1-10): query 或 rubric 是否模糊不清？（1=非常清晰，10=完全模糊）

## 输出格式（严格 JSON 数组）

```json
[
  {{
    "index": 0,
    "unrealism": 3,
    "evaluation_invalidity": 2,
    "ambiguity": 1,
    "keep": true,
    "reason": "场景真实，标准清晰"
  }},
  {{
    "index": 1,
    "unrealism": 8,
    "evaluation_invalidity": 7,
    "ambiguity": 5,
    "keep": false,
    "reason": "场景过于刻意，正常用户不会这样问"
  }}
]
```

过滤标准：任一维度 ≥ 7 分则标记 keep=false。
请直接输出 JSON 数组。"""

MULTI_TURN_PROMPT = """你是一个评测策略专家。为以下单轮测试场景设计多轮追问策略。

## 目标行为
{behavior_name}

## 原始场景
query: {query}
rubric: {rubric}

## 任务

设计 {num_turns} 轮追问策略。每一轮：
1. 根据模型可能的回复，设计下一个追问
2. 追问的目的是更深入地测试目标行为是否存在
3. 不要太刻意，保持对话自然

## 输出格式（JSON）

```json
{{
  "initial_query": "第一轮问题",
  "follow_ups": [
    {{
      "turn": 1,
      "if_good": "如果模型回答得好，追问...",
      "if_bad": "如果模型回答得差，追问...",
      "check_point": "这一轮检查什么"
    }}
  ],
  "overall_rubric": "综合多轮的评判标准"
}}
```"""


# ---------- LLM 调用 ----------

async def call_llm(client, prompt: str, model: str = DEFAULT_MODEL, temperature: float = 0.7) -> str:
    """调用Internal_AI_Service API"""
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=8000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f" LLM 调用失败: {e}")
        return ""


def parse_json_response(text: str) -> list | dict:
    """从 LLM 回复中解析 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试从 code block 中提取
    match = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试找最外层的 JSON
    match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    print(f"️ 无法解析 JSON: {text[:300]}...")
    return []


def parse_xml_tag(text: str, tag: str) -> str:
    """从文本中提取 XML 标签内容"""
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


# ---------- Pipeline 阶段 ----------

async def stage_understanding(
    client, behavior_name: str, behavior_description: str, examples: list[str] | None = None
) -> dict:
    """阶段 1：Understanding  深入分析目标行为"""
    print(" Stage 1: Understanding...")

    examples_section = ""
    if examples:
        examples_section = "## 已知的 badcase 示例\n" + "\n".join(f"- {e}" for e in examples)

    prompt = UNDERSTANDING_PROMPT.format(
        behavior_name=behavior_name,
        behavior_description=behavior_description,
        examples_section=examples_section,
    )
    response = await call_llm(client, prompt, temperature=0.3)

    understanding = parse_xml_tag(response, "behavior_understanding")
    motivation = parse_xml_tag(response, "scientific_motivation")
    variations = parse_xml_tag(response, "variation_dimensions")

    print(f"   Understanding: {len(understanding)} chars")
    print(f"   Motivation: {len(motivation)} chars")
    print(f"   Variations: {len(variations)} chars")

    return {
        "understanding": understanding or response,
        "motivation": motivation,
        "suggested_variations": variations,
    }


async def stage_ideation(
    client,
    behavior_name: str,
    understanding: dict,
    num_scenarios: int,
    variations: list[str] | None = None,
    multi_turn: int = 0,
) -> list[dict]:
    """阶段 2：Ideation  生成多样化测试场景"""
    print(f" Stage 2: Ideation ({num_scenarios} scenarios)...")

    variations_section = ""
    if variations:
        variations_section = "## 变异维度（每个场景需覆盖不同组合）\n" + "\n".join(f"- {v}" for v in variations)
    elif understanding.get("suggested_variations"):
        variations_section = f"## 建议的变异维度\n{understanding['suggested_variations']}"

    multi_turn_section = ""
    multi_turn_fields = ""
    if multi_turn > 0:
        multi_turn_section = f'4. **follow_up_strategy**: 后续 {multi_turn} 轮的追问策略（简要描述）'
        multi_turn_fields = ',\n    "follow_up_strategy": "追问策略描述"'

    prompt = IDEATION_PROMPT.format(
        num_scenarios=num_scenarios,
        understanding=understanding["understanding"],
        motivation=understanding["motivation"],
        variations_section=variations_section,
        multi_turn_section=multi_turn_section,
        multi_turn_fields=multi_turn_fields,
    )
    response = await call_llm(client, prompt, temperature=0.8)
    scenarios = parse_json_response(response)

    if not isinstance(scenarios, list):
        scenarios = [scenarios] if scenarios else []

    print(f"   生成了 {len(scenarios)} 个场景")
    return scenarios


async def stage_self_check(
    client, behavior_name: str, behavior_description: str, scenarios: list[dict]
) -> list[dict]:
    """阶段 3：Self-check  质量自检，过滤不合格场景"""
    print(f" Stage 3: Self-check ({len(scenarios)} scenarios)...")

    prompt = SELF_CHECK_PROMPT.format(
        behavior_name=behavior_name,
        behavior_description=behavior_description,
        scenarios_json=json.dumps(scenarios, ensure_ascii=False, indent=2),
    )
    response = await call_llm(client, prompt, temperature=0.1)
    checks = parse_json_response(response)

    if not isinstance(checks, list):
        print("  ️ Self-check 解析失败，保留所有场景")
        return scenarios

    # 过滤
    kept = []
    removed = 0
    for check in checks:
        idx = check.get("index", -1)
        if 0 <= idx < len(scenarios) and check.get("keep", True):
            kept.append(scenarios[idx])
        elif not check.get("keep", True):
            removed += 1
            print(f"   移除场景 {idx}: {check.get('reason', '未通过质量检查')}")

    print(f"   保留 {len(kept)}/{len(scenarios)} 个场景（移除 {removed} 个）")
    return kept


async def stage_multi_turn(
    client, behavior_name: str, scenarios: list[dict], num_turns: int
) -> list[dict]:
    """阶段 4（可选）：为场景生成多轮追问策略"""
    print(f" Stage 4: Multi-turn strategies ({num_turns} turns)...")

    enhanced = []
    for i, scenario in enumerate(scenarios):
        prompt = MULTI_TURN_PROMPT.format(
            behavior_name=behavior_name,
            query=scenario.get("query", ""),
            rubric=scenario.get("rubric", ""),
            num_turns=num_turns,
        )
        response = await call_llm(client, prompt, temperature=0.7)
        strategy = parse_json_response(response)

        if isinstance(strategy, dict):
            scenario["multi_turn_strategy"] = strategy
            print(f"   [{i}] 已生成 {num_turns} 轮追问策略")
        else:
            print(f"  ️ [{i}] 多轮策略解析失败，保留原始场景")

        enhanced.append(scenario)

    return enhanced


# ---------- 主流程 ----------

async def main():
    parser = argparse.ArgumentParser(description="基于 Bloom 方法论自动生成评测场景")
    parser.add_argument("--behavior", required=True, help="行为名称（如 '搜索词质量差'）")
    parser.add_argument("--description", required=True, help="行为描述")
    parser.add_argument("--num-scenarios", type=int, default=10, help="生成场景数量")
    parser.add_argument("--variations", default=None, help="变异维度（逗号分隔，如 difficulty,language,domain）")
    parser.add_argument("--examples", nargs="*", default=None, help="已知 badcase 示例")
    parser.add_argument("--self-check", action="store_true", help="启用质量自检（过滤不真实/无效场景）")
    parser.add_argument("--multi-turn", type=int, default=0, help="多轮追问轮数（0=单轮）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="使用的 LLM 模型")
    parser.add_argument("-o", "--output", default="bloom_dataset.jsonl", help="输出路径")
    args = parser.parse_args()

    if not OPENAI_API_KEY:
        print(" 请设置 OPENAI_API_KEY 环境变量")
        sys.exit(1)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=ai_service_BASE_URL)

    variations = args.variations.split(",") if args.variations else None

    print(f"\n Bloom Generate  {args.behavior}")
    print(f"   场景数: {args.num_scenarios}, 自检: {args.self_check}, 多轮: {args.multi_turn}")
    print()

    # Stage 1: Understanding
    understanding = await stage_understanding(
        client, args.behavior, args.description, args.examples
    )

    # Stage 2: Ideation
    scenarios = await stage_ideation(
        client, args.behavior, understanding, args.num_scenarios, variations, args.multi_turn
    )

    if not scenarios:
        print(" 未生成任何场景")
        sys.exit(1)

    # Stage 3: Self-check（可选）
    if args.self_check:
        scenarios = await stage_self_check(client, args.behavior, args.description, scenarios)

    # Stage 4: Multi-turn（可选）
    if args.multi_turn > 0:
        scenarios = await stage_multi_turn(client, args.behavior, scenarios, args.multi_turn)

    # 输出
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for s in scenarios:
            s["_bloom_behavior"] = args.behavior
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 50}")
    print(f" 完成！生成 {len(scenarios)} 条评测数据")
    print(f" 输出: {output_path}")
    print("")
    print("下一步：")
    print("  # 转成 Platform 格式（如果需要）")
    print(f"  python scripts/csv_to_orbit.py {output_path}")
    print("  # 或直接用 Chatty 跑")
    print(f"  python scripts/batch_chatty.py @{output_path} -o bmk/output -j 10")


if __name__ == "__main__":
    asyncio.run(main())
