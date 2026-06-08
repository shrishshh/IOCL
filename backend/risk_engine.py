"""
Pure-function risk engine — no pandas, no CSV.
Operates on a list of item dicts:
  {"section": str, "item_id": str, "response": "Yes"|"No"|"NA",
   "remark": str, "risk_label": "Low"|"Medium"|"High"}
"""

W_NUMERICAL, W_SEMANTIC = 0.40, 0.60
LOW_BELOW, HIGH_AT = 15, 25

# Maps department name (users.department) -> section string in checklist items
DEPT_SECTIONS: dict[str, str] = {
    "PPE": "PPE",
    "Housekeeping": "Housekeeping",
    "Permits": "Permits",
    "Electrical": "Electrical_Safety",
    "Hydrocarbon": "Hydrocarbon_Safety",
    "Emergency": "Emergency_Procedures",
    "Confined": "Confined_Space",
    "Welding": "Cutting_Welding_Grinding",
    "Documentation": "Documentation",
}


def _compliance(items: list[dict]) -> float:
    yes = sum(1 for it in items if it["response"] == "Yes")
    no  = sum(1 for it in items if it["response"] == "No")
    return round(100 * yes / (yes + no), 2) if (yes + no) else 0.0


def _section_scores(items: list[dict]) -> dict[str, float]:
    buckets: dict[str, dict] = {}
    for it in items:
        sec = it["section"]
        if sec not in buckets:
            buckets[sec] = {"yes": 0, "no": 0}
        if it["response"] == "Yes":
            buckets[sec]["yes"] += 1
        elif it["response"] == "No":
            buckets[sec]["no"] += 1
    out = {}
    for sec, c in buckets.items():
        y, n = c["yes"], c["no"]
        if y + n > 0:
            out[sec] = round(100 * y / (y + n), 2)
    return out


def _numerical_score(comp: float) -> float:
    return round(100 - comp, 2)


def _semantic_score(label_counts: dict) -> float:
    H = label_counts.get("High", 0)
    M = label_counts.get("Medium", 0)
    L = label_counts.get("Low", 0)
    total = H + M + L
    return round((2 * H + 1 * M) / total * 100, 2) if total else 0.0


def _final_index(num: float, sem: float) -> float:
    return round(W_NUMERICAL * num + W_SEMANTIC * sem, 2)


def _final_risk(idx: float) -> str:
    if idx >= HIGH_AT:
        return "High"
    if idx >= LOW_BELOW:
        return "Medium"
    return "Low"


def section_scores(items: list[dict]) -> dict[str, float]:
    """Public alias — compliance score per section (only sections with Yes/No)."""
    return _section_scores(items)


def assess(items: list[dict]) -> dict:
    """
    Takes a list of item dicts (each must have 'response' and 'risk_label').
    Returns the full risk payload.
    """
    comp = _compliance(items)

    label_counts: dict[str, int] = {}
    for it in items:
        lbl = it["risk_label"]
        label_counts[lbl] = label_counts.get(lbl, 0) + 1

    num = _numerical_score(comp)
    sem = _semantic_score(label_counts)
    idx = _final_index(num, sem)
    secs = _section_scores(items)

    hidden = sum(
        1 for it in items
        if it["response"] == "Yes" and it["risk_label"] == "High"
    )

    section_flags = {
        s: v
        for s, v in sorted(secs.items(), key=lambda x: x[1])
        if v < 70
    }

    return {
        "overall_risk": _final_risk(idx),
        "final_risk_index": idx,
        "compliance_score": comp,
        "numerical_risk_score": num,
        "semantic_risk_score": sem,
        "hidden_risks": hidden,
        "section_flags": section_flags,
        "label_counts": label_counts,
    }


def assess_by_department(items: list[dict]) -> dict[str, dict]:
    """
    Same formulas as assess(), but computed separately for each department's
    mapped section. Skips departments that have no Yes/No items.
    Returns: {dept_name: {compliance, numerical_risk, semantic_risk,
                          final_index, risk_band, hidden_risks}}
    """
    out: dict[str, dict] = {}
    for dept, section in DEPT_SECTIONS.items():
        dept_items = [it for it in items if it["section"] == section]
        if not any(it["response"] in ("Yes", "No") for it in dept_items):
            continue

        comp = _compliance(dept_items)
        label_counts: dict[str, int] = {}
        for it in dept_items:
            lbl = it["risk_label"]
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

        num = _numerical_score(comp)
        sem = _semantic_score(label_counts)
        idx = _final_index(num, sem)
        hidden = sum(
            1 for it in dept_items
            if it["response"] == "Yes" and it["risk_label"] == "High"
        )
        out[dept] = {
            "compliance": comp,
            "numerical_risk": num,
            "semantic_risk": sem,
            "final_index": idx,
            "risk_band": _final_risk(idx),
            "hidden_risks": hidden,
        }
    return out
