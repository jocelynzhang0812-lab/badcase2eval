"""
Judge prompts for search badcase BMK evaluation.

Usage:
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt_at_1(query, criteria, model_response)}
        ],
        response_format={"type": "json_object"}
    )
"""

SYSTEM_PROMPT = """\
You are a strict evaluation judge. You will be given a user question, a set of scoring criteria, and a model's response. Your job is to determine whether the model's response satisfies ALL the scoring criteria.

Rules:
1. Evaluate EACH criterion independently first, then give an overall score.
2. A criterion is "met" only if the response clearly and unambiguously satisfies it.
3. Ignore formatting, citation markers, and filler text  focus on substance.
4. If the criteria mention searching or using up-to-date information, check whether the response content reflects current/recent information rather than outdated facts.

Scoring:
- 1   = ALL criteria are fully met.
- 0.5 = SOME criteria are met but not all, or a criterion is partially satisfied.
- 0   = NONE of the criteria are met, or the response is a refusal / "I don't know".

Output a JSON object with exactly these fields:
- "score": 1, 0.5, or 0
- "reason": a brief (1-2 sentence) explanation of your judgment\
"""


def user_prompt_at_1(query: str, criteria: str, model_response: str) -> str:
    """Single-sample judge prompt."""
    return f"""\
Question: {query}

Scoring criteria:
{criteria}

Model response:
{model_response}

Judge the model response against the scoring criteria.\
"""


def user_prompt_at_n(samples: list[dict]) -> str:
    """Batch judge prompt for multiple samples in one request.

    Each item in `samples` should have keys: index, query, criteria, model_response.
    """
    parts = []
    for s in samples:
        parts.append(
            f"[Sample {s['index']}]\n"
            f"Question: {s['query']}\n"
            f"Scoring criteria:\n{s['criteria']}\n"
            f"Model response:\n{s['model_response']}"
        )
    block = "\n\n---\n\n".join(parts)

    return f"""\
Judge each sample below. Return a JSON object with a "results" array, where each element has "index", "score", and "reason".

{block}\
"""
