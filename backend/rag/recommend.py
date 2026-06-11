"""
RAG recommender: combines retrieved OISD-STD-225 excerpts with a Groq LLM call
to generate a grounded corrective-action recommendation for a flagged item.
"""
from .retriever import retrieve
from .llm       import generate

_SYSTEM = (
    "You are an IOCL retail-outlet safety advisor. "
    "Using ONLY the provided OISD-STD-225 excerpts, give a concise 2-4 sentence "
    "corrective action for the flagged inspection item, and cite the relevant section "
    "(e.g. 'per OISD-STD-225 Section 10'). "
    "If the excerpts do not cover the item, provide general OISD-aligned best practice "
    "and explicitly note that the specific clause was not found in the excerpts. "
    "Do NOT invent specific numerical thresholds or quantities that are not present in "
    "the excerpts."
)


def _build_query(question: str, remark: str, section: str) -> str:
    parts = [section.replace("_", " ")]
    if question:
        parts.append(question)
    if remark:
        parts.append(remark)
    return " ".join(parts)


def recommend_for_item(
    question:   str,
    response:   str,
    remark:     str,
    risk_label: str,
    section:    str,
) -> dict:
    """
    Generate a grounded corrective-action recommendation.

    Returns {"text": str | None, "cited_sections": list[str]}.
    text is None if retrieval failed, the vectorstore is empty, or the LLM call
    failed — caller must handle None gracefully.
    """
    query    = _build_query(question, remark, section)
    excerpts = retrieve(query, k=4)

    if not excerpts:
        return {"text": None, "cited_sections": []}

    excerpt_block = "\n\n".join(
        f"[Section {e['section']} — {e['section_name']}]\n{e['text']}"
        for e in excerpts
    )
    cited_sections = [e["section"] for e in excerpts]

    user_prompt = (
        f"Flagged inspection item:\n"
        f"  Section   : {section.replace('_', ' ')}\n"
        f"  Question  : {question or '(not specified)'}\n"
        f"  Response  : {response}\n"
        f"  Remark    : {remark or '(none)'}\n"
        f"  Risk level: {risk_label}\n\n"
        f"Relevant OISD-STD-225 excerpts:\n{excerpt_block}\n\n"
        f"Provide a concise corrective action for this item."
    )

    text = generate(_SYSTEM, user_prompt)
    return {"text": text, "cited_sections": cited_sections}
