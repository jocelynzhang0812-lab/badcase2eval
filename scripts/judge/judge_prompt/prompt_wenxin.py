"""
Search result evaluation prompts (wenxin style).

Four dimensions: timeliness, authority, completeness, citation_compliance.
Each dimension scores 0 or 1.

Usage:
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt_at_1(query, answer, search_meta, criteria)}
        ],
        response_format={"type": "json_object"}
    )
"""

SYSTEM_PROMPT = """\
You are a professional search evaluation expert with strong capabilities in assessing information quality across official sources, mainstream media, academic publications, and online search results.

Your task is to score a model's output across four dimensions. Each dimension receives either 1 (pass) or 0 (fail).

---

## 1. Timeliness (0/1)

Give 1 only if ALL conditions are satisfied:
- All cited sources fall within the time range required by the user query.
- No main evidence relies on sources published 1 year or more ago, unless clearly used as background context.
- Current time is 2026-02-13, and the answer correctly understands and uses the current timeline without temporal mistakes.

Give 0 if ANY of the following occurs:
- Sources fall outside the required time range.
- Event timeline or current status is misinterpreted.
- Sources >=1 year old are used as main supporting evidence (unless clearly background context).

## 2. Authority (0/1)

Give 1 only if ALL conditions are satisfied:
- Main information comes from: official institutions, mainstream authoritative media, academic institutions or research reports.
- Non-authoritative or secondary sources account for <=20% of evidence.

Give 0 if ANY of the following occurs:
- Main evidence comes from: marketing blogs, self-media accounts, forums, anonymous blogs, or unverifiable sources.

## 3. Information Completeness (0/1)

Give 1 only if ALL conditions are satisfied:
- Information directly supports the task without requiring further user search.
- Key elements are complete (5W1H, required data, dates, versions, quantities, or specifications).
- Users can directly use the result without missing critical details.

Give 0 if ANY of the following occurs:
- Missing key information forces further search.
- Only vague or incomplete descriptions are provided.

## 4. Citation Compliance (0/1)

Give 1 only if ALL conditions are satisfied:
- Key factual claims include clear source attribution.
- Citations correctly correspond to statements.
- Citation format follows: [^N^].

Give 0 if ANY of the following occurs:
- Many important claims lack citations.
- Citations do not match referenced content.

---

Return evaluation results strictly as a JSON object with scores and reasons for each dimension. Do NOT include a total score. Output JSON only, no additional text.\
"""


def user_prompt_at_1(
    query: str,
    answer: str,
    search_meta: str,
    criteria: str = "",
) -> str:
    """Single-sample evaluation prompt.

    Args:
        query: Original user query.
        answer: Model's output to evaluate.
        search_meta: Search result metadata (from tool_end display_contents).
        criteria: Optional scoring criteria (打分点) from BMK.
    """
    parts = [f"User query: {query}"]

    if search_meta.strip():
        parts.append(f"Search results:\n{search_meta}")

    parts.append(f"Model output:\n{answer}")

    if criteria.strip():
        parts.append(f"Additional scoring criteria:\n{criteria}")

    parts.append("Evaluate the model output across the four dimensions.")

    return "\n\n".join(parts)


def user_prompt_at_n(samples: list[dict]) -> str:
    """Batch evaluation prompt for multiple samples in one request.

    Each item in `samples` should have keys: index, query, answer, search_meta, criteria (optional).
    """
    parts = []
    for s in samples:
        block = [f"[Sample {s['index']}]", f"User query: {s['query']}"]
        if s.get("search_meta", "").strip():
            block.append(f"Search results:\n{s['search_meta']}")
        block.append(f"Model output:\n{s['answer']}")
        if s.get("criteria", "").strip():
            block.append(f"Additional scoring criteria:\n{s['criteria']}")
        parts.append("\n".join(block))

    block = "\n\n---\n\n".join(parts)

    return f"""\
Evaluate each sample below. Return a JSON object with a "results" array, where each element has "index", "timeliness", "authority", "completeness", and "citation_compliance" (each with "score" and "reason").

{block}\
"""
