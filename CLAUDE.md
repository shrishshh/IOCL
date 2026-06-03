# IOCL RO Safety — Project Context

> Drop this file at the repo root (`d:\IOCL\CLAUDE.md`). Claude Code reads it automatically.
> Keep it updated as the project evolves.

## What this project is
An internship project that analyses **IOCL Retail Outlet (petrol pump) safety inspections**.
Inspections use the OISD-GDN-192 Annexure IV checklist: ~144 items, each with a **Yes/No/NA**
box and a free-text **Remark**.

The core idea: traditional analysis only counts the Yes/No boxes (a compliance %) and **misses
hidden risk buried in the remarks** — e.g. an item ticked "Yes" whose remark says "extinguisher
present BUT pressure below minimum". This project catches that by running two pipelines and
fusing them.

Final deliverable: a **PWA** where an officer submits a filled checklist and sees an overall
risk readout (the dashboard mockup: overall risk, scores, section flags, hidden-risk count,
and later an AI recommendation panel).

## Architecture
```
Officer fills checklist (144 items: Yes/No/NA + Remark)
        │
   ┌────┴─────┐
   ▼          ▼
NUMERICAL   SEMANTIC
(formula)   (BERT + Logistic Regression on remarks → Low/Med/High per remark)
   │          │
   └────┬─────┘
        ▼
 COMBINED RISK ENGINE  →  Final Risk Index = 0.40*numerical + 0.60*semantic
        ▼
 Backend API (FastAPI) → PWA front end
```
A **LLaMA + RAG recommendation layer** is planned but **deferred** until the project guide
provides the "suggestion rule book". It does NOT block anything — the Final Risk Index does
not depend on it. Leave a placeholder panel in the PWA.

## Repository structure
```
IOCL/
├── CLAUDE.md
├── IOCL_Combined_Risk_Engine.ipynb     # engine logic (reference)
├── NumericalAnalysis/
│   ├── IOCL_Inspection_Dataset.csv      # 102,528 rows, one per checklist item (raw)
│   ├── IOCL_Inspection_Summary.csv      # 712 rows, one per inspection (precomputed)
│   └── IOCL_Numerical_Analysis.ipynb
├── SymanticAnalysis/                    # NOTE: folder is misspelled "Symantic" — keep consistent
│   ├── IOCL_Model_Training_CV.ipynb
│   ├── IOCL_Remarks_ML_Expanded.csv     # 12,473 unique remarks, 559 groups (USE THIS one)
│   └── risk_classifier_bundle.pkl       # the trained semantic model bundle
└── backend/
    ├── __init__.py
    ├── risk_engine.py      # pure functions, no pandas
    ├── classifier.py       # loads bundle + SentenceTransformer once at import
    ├── schemas.py          # Pydantic models
    ├── main.py             # FastAPI: /health, /assess
    ├── requirements.txt
    └── test_request.py
```

## Risk scoring logic — EXACT, do not change without reason
Per item: `response ∈ {Yes, No, NA}`, `risk_label ∈ {Low, Medium, High}` (label predicted by BERT).

- **compliance** = `Yes / (Yes + No) * 100`  (NA excluded)
- **section score** = same formula restricted to that section; **skip sections with no Yes/No** (all-NA = not applicable, don't score as 0)
- **numerical_risk_score** = `100 - compliance`  (0 = safe, higher = riskier)
- **semantic_risk_score** = `(2*#High + 1*#Medium) / total_items * 100`  (matches the dataset's own formula exactly)
- **final_risk_index** = `0.40 * numerical_risk_score + 0.60 * semantic_risk_score`
- **risk band**: `index >= 25 → High` ; `index >= 15 → Medium` ; else `Low`
- **hidden_risks** = count of items where `response == "Yes" AND risk_label == "High"`
- **section_flags** = sections with score `< 70`

Weights (40/60) and thresholds (15/25, 70) are **tunable policy choices, NOT learned**. They can
be changed if the guide wants. The High cutoff of 25 reproduces the dataset's own labels ~92%.

## Semantic model (the BERT side)
- Encoder: **`all-MiniLM-L6-v2`** (sentence-transformers), used **frozen** (not fine-tuned) → 384-dim vectors.
- Classifier: **Logistic Regression** on those vectors (chosen by 5-fold GroupKFold cross-validation).
- Performance: ~**79% CV accuracy** (±5), ~**0.83** held-out macro-F1. Medium class is the weakest.
- Bundle contents (`risk_classifier_bundle.pkl`): `classifier`, `encoder_name`, `labels`, `embedding_dim`, `cv_macro_f1`.
- Usage: encode remark text with the encoder → `classifier.predict` → map index through `labels`.
  The `.pkl` does NOT contain the encoder; load `SentenceTransformer(bundle["encoder_name"])` separately.

### Why frozen BERT + Logistic Regression (not deep learning / fine-tuning)
- The data is limited and synthetic (see below); fine-tuning would overfit and inflate scores.
- BERT embeddings already carry the deep-learned semantics; a linear classifier suits dense embeddings.
- On dense embeddings, linear/LogReg beats tree models (RF/XGB) — this is expected, not a bug.
- Explainable and reproducible for the guide.

## Data notes & history (important)
- **Use `IOCL_Remarks_ML_Expanded.csv`** for the semantic model. Do NOT use `IOCL_Remarks_ML_Dataset.csv`
  (75,597 rows) — it caused **data leakage** (a 563-base-remark pool repeated across rows; a random
  split put identical text in train+test → fake ~100% accuracy). The Expanded set is de-duplicated
  with a `remark_group` column; always split with **GroupShuffleSplit / GroupKFold on `remark_group`**.
- All data is **synthetic**, generated from ~563 base remarks across RO profiles (Good/Average/Poor).
  So accuracy numbers are an **optimistic ceiling**; real field remarks will be messier.
- In this synthetic data, compliance and semantic risk are **~ -0.98 correlated** (they mostly agree).
  The combined engine matters most on the rare cases where they **disagree** (the hidden-risk cases).
- `overall_risk_level` in the data is the *combined* label (High/Medium only — no Low present).

## Status & roadmap
- [x] Semantic pipeline (BERT + LogReg), cross-validated, bundle saved
- [x] Numerical pipeline (compliance formula), validated to 0.0 diff vs Summary
- [x] Combined Risk Engine (40/60), validated ~90.9% vs dataset labels
- [x] Backend API scaffolded and verified (FastAPI) — `/health` and `/assess` both return clean JSON; run with `py -3.11 -m uvicorn backend.main:app --port 8000`
- [x] **PWA front end** — 144-item checklist (21 sections, accordion layout) → POST /assess → dashboard with risk band, 4 score cards, section flags, hidden-risk count, AI placeholder; served by FastAPI at `/`
- [ ] (Deferred) LLaMA + RAG recommendation panel — when the guide provides the rule book

## Backend contract
- `GET /health` → `{"status":"ok"}`
- `POST /assess` body: `{inspection_id, ro_name, items:[{section, item_id, response, remark}]}`
  Flow: predict `risk_label` for each remark via the BERT bundle, attach it, then call `assess(items)`.
  Returns: `{overall_risk, final_risk_index, compliance_score, numerical_risk_score,
  semantic_risk_score, hidden_risks, section_flags}`.
- CORS enabled for the front end. First request is slow (encoder warmup).

## Gotchas / conventions
- The folder is literally named **`SymanticAnalysis`** (misspelled). Match it exactly in paths.
- Resolve the `.pkl` path relative to repo root (pathlib), never hardcode an absolute path.
- The serving path must stay **pandas-free**; pandas is only for the analysis notebooks.
- In production, `hidden_risks` comes from BERT predictions (~83% accurate), so it will vary slightly
  from the dataset's stored labels — this is expected.
- Tech stack: Python 3.12, FastAPI, sentence-transformers, scikit-learn. Front end: PWA (to be built).
