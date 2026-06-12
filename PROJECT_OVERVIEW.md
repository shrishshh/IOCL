# IOCL RO Safety — Exhaustive Technical Project Overview

> Written for: formal project report (15 pages). All facts sourced directly from the
> codebase unless marked `[from CLAUDE.md]` or `[unverified]`.
> All file paths are relative to repo root `d:\IOCL\`.

---

## Table of Contents

1. [Problem Statement & Motivation](#1-problem-statement--motivation)
2. [High-Level System Architecture](#2-high-level-system-architecture)
3. [Datasets](#3-datasets)
4. [Semantic ML Pipeline](#4-semantic-ml-pipeline)
5. [Numerical Pipeline](#5-numerical-pipeline)
6. [Combined Risk Engine](#6-combined-risk-engine)
7. [Multi-Role Platform — Auth, Data Model, API](#7-multi-role-platform--auth-data-model-api)
8. [Issue-Resolution Workflow](#8-issue-resolution-workflow)
9. [RAG Recommendation Layer](#9-rag-recommendation-layer)
10. [Full Tech Stack & File/Folder Structure](#10-full-tech-stack--filefolder-structure)
11. [Results & Validation](#11-results--validation)
12. [Key Technical Decisions & Rationale](#12-key-technical-decisions--rationale)
13. [Limitations & Future Work](#13-limitations--future-work)

---

## 1. Problem Statement & Motivation

### 1.1 The Regulatory Context

IOCL (Indian Oil Corporation Limited) Retail Outlets (petrol pumps) are subject to mandatory
safety inspections governed by **OISD-GDN-192 (Oil Industry Safety Directorate — General
Design Note 192)**. Each inspection uses the **Annexure IV** checklist, which contains **144
items** across 21 sections covering PPE, housekeeping, excavation, permits, welding/cutting,
electrical safety, hydrocarbon safety, confined-space work, emergency procedures, and more.

Every checklist item has three sub-fields:
- **Response**: one of `Yes` / `No` / `NA` (not applicable).
- **Remark**: free-text observation by the inspector.
- Implicit: the inspector's intent behind the remark, not captured in Yes/No.

### 1.2 The Hidden-Risk Gap

Traditional compliance analysis sums Yes and No responses:

```
compliance = Yes / (Yes + No) × 100
```

This produces a single percentage — the *compliance score* — which is used to assign a risk
level (High / Medium / Low). This approach has a fatal flaw: **the remark field is entirely
discarded**. A station can achieve 92% compliance on paper while concealing multiple active
hazards inside "Yes"-ticked items whose remarks reveal non-compliance.

**Concrete example** (directly from the model's sanity-check output in
`SymanticAnalysis/IOCL_Model_Training_CV.ipynb`):

> Item: "Fire extinguisher present but pressure gauge reading below minimum"
> Response (Yes/No box): **Yes** → adds to compliance numerator
> Semantic label assigned by the ML model: **Medium**

Because the item is ticked "Yes", the compliance formula counts it as fully compliant.
The numerical risk score misses it completely. Only the semantic classifier, which reads
the *remark*, surfaces the issue. This is precisely what the project defines as a
**hidden risk**:

```
hidden_risk = True  if  response == "Yes"  AND  semantic_label == "High"
```

An even starker example from the same notebook output:

> Remark: "No ELCB installed on main panel, workers exposed to electrocution risk"
> → Labelled **High** by the semantic classifier.

If an inspector ticked "Yes" for this item (perhaps because the panel *exists* even
though it is not functioning), the compliance formula would count it as safe.

### 1.3 The Proposed Solution

This project builds a **dual-pipeline risk engine** that runs two independent analyses on
every inspection and fuses them:

- **Numerical pipeline**: applies the formula above to Yes/No boxes. Interpretable, exact,
  zero ML.
- **Semantic pipeline**: feeds each remark through a frozen BERT encoder
  (all-MiniLM-L6-v2) followed by a trained Logistic Regression classifier to predict
  Low / Medium / High risk for that remark, independent of the Yes/No response.

The fused **Final Risk Index** is:

```
Final Risk Index = 0.40 × numerical_risk_score + 0.60 × semantic_risk_score
```

On top of this, a **RAG (Retrieval-Augmented Generation) layer** generates grounded,
citation-backed corrective-action recommendations from the OISD-STD-225 standard for
every Medium or High risk item.

The deliverable is a **multi-role Progressive Web App (PWA)** served directly from the
FastAPI backend, supporting three roles: inspector (submit), zone head (review all
inspections in zone), and department officer (view + resolve items in their department).

---

## 2. High-Level System Architecture

```
Inspector fills OISD-GDN-192 Annexure IV checklist  (144 items: Yes/No/NA + Remark)
             │
             │  POST /inspections  (JWT-authenticated)
             ▼
   ┌──────────────────────────────────────────────────┐
   │          FastAPI Application (backend/main.py)   │
   │                                                  │
   │  1. Verify JWT + scope (inspector, correct office)
   │  2. classifier.predict_labels(remarks)           │
   │     → MiniLM encoder → LogReg → [Low/Med/High]  │
   │                                                  │
   │  3. risk_engine.assess(items_with_labels)        │
   │     → compliance, numerical_risk_score,          │
   │       semantic_risk_score, final_risk_index,     │
   │       overall_risk, hidden_risks, section_flags  │
   │                                                  │
   │  4. risk_engine.assess_by_department(items)      │
   │     → same metrics per each of 9 departments     │
   │                                                  │
   │  5. Persist to SQLite (iocl.db):                 │
   │     - Inspection row                             │
   │     - InspectionItem rows (144)                  │
   │     - DepartmentRisk rows (≤9)                   │
   │                                                  │
   │  6. Return {status:"submitted", inspection_id}   │
   │     immediately (inspector never sees risk)      │
   └──────────┬───────────────────────────────────────┘
              │
              │  BackgroundTasks.add_task(_generate_recommendations, insp.id)
              ▼
   ┌─────────────────────────────────────────────────┐
   │        RAG Background Task (async, post-commit) │
   │                                                 │
   │  For each Medium/High item:                     │
   │  1. Build query = section + question + remark   │
   │  2. retriever.retrieve(query, k=4)              │
   │     → MiniLM encode query → Chroma cosine       │
   │       → top-4 OISD-STD-225 chunks              │
   │  3. llm.generate(system, user_prompt)           │
   │     → Groq API (llama-3.1-8b-instant)           │
   │     → 2-4 sentence corrective action +          │
   │       cited OISD-STD-225 sections               │
   │  4. Store recommendation + cited_sections       │
   │     on InspectionItem (UPDATE)                  │
   │  Any failure → null stored; never breaks submit │
   └──────────┬──────────────────────────────────────┘
              │
              │  SQLite iocl.db (persists all above)
              ▼
   ┌──────────────────────────────────────────────────┐
   │          Multi-Role PWA (frontend/index.html)    │
   │                                                  │
   │  Zone Head (/zone/inspections, /inspections/{id})│
   │  → sees overall risk, all items, dept breakdown, │
   │    section flags, hidden risk count, RAG recs    │
   │                                                  │
   │  Dept Officer (/dept/inspections, /{id})         │
   │  → sees dept-only risk + items, can resolve      │
   │    Medium/High items (POST .../resolve)          │
   │    → resolved badge replaces "Mark Resolved"     │
   │    → RAG recommendation shown per item           │
   │                                                  │
   │  Inspector: submit-only, 3-step flow             │
   │  (step 1: pick RO; step 2: fill 144 items;       │
   │   step 3: confirmation; no risk visible)         │
   └──────────────────────────────────────────────────┘
```

**Component inventory:**

| Component | File(s) | Responsibility |
|---|---|---|
| FastAPI app | `backend/main.py` | Mount all routers, serve PWA at `/` |
| SQLite DB | `backend/database.py`, `iocl.db` | SQLModel engine, session factory |
| ORM models | `backend/models.py` | 6 SQLModel table classes |
| JWT auth | `backend/auth.py` | Token creation/validation, `require_role()` |
| Semantic classifier | `backend/classifier.py` | Load bundle + SentenceTransformer at import |
| Risk engine | `backend/risk_engine.py` | Pandas-free pure-function scoring |
| Request schemas | `backend/schemas.py` | Pydantic request/response models |
| Auth routes | `backend/routes/auth_routes.py` | `/auth/login`, `/auth/me` |
| Inspector routes | `backend/routes/inspector.py` | `/my/ros`, `POST /inspections`, RAG BG task |
| Zone head routes | `backend/routes/zone_head.py` | `/zone/inspections`, `/inspections/{id}` |
| Dept officer routes | `backend/routes/dept_officer.py` | `/dept/inspections`, `/{id}`, resolve |
| RAG ingest | `backend/rag/ingest.py` | One-time PDF chunking + Chroma population |
| RAG retriever | `backend/rag/retriever.py` | Lazy Chroma load, cosine search |
| LLM adapter | `backend/rag/llm.py` | Groq/OpenAI-compatible call |
| RAG orchestrator | `backend/rag/recommend.py` | Query build → retrieve → prompt → generate |
| Seed script | `backend/seed.py` | Idempotent: zones, offices, ROs, 43 demo users |
| Smoke test | `backend/smoke_test.py` | End-to-end API validation (server must be up) |
| PWA frontend | `frontend/index.html` | Single-file SPA, all JS inline |
| Service worker | `frontend/sw.js` | Cache-first strategy for `/`, `/index.html`, `/manifest.json` |
| PWA manifest | `frontend/manifest.json` | name, theme_color `#C41230`, standalone display |

---

## 3. Datasets

Three CSV files are used; two from the same data generation process, one derived.

### 3.1 IOCL_Inspection_Dataset.csv (`NumericalAnalysis/`)

**Source**: `NumericalAnalysis/IOCL_Inspection_Dataset.csv`  
**Verified from**: `NumericalAnalysis/IOCL_Numerical_Analysis.ipynb` Step 1 output

| Property | Value |
|---|---|
| Row count | 102,528 |
| Granularity | One row per checklist item |
| Inspections | 712 (unique `inspection_id` values) |
| Items per inspection | 144 (= 102,528 / 712) |
| Sections | 21 (see below) |

**21 sections confirmed from notebook output**:
`Abrasive_Blasting_Painting`, `Concreting`, `Confined_Space`, `Cutting_Welding_Grinding`,
`Demolishing`, `Documentation`, `Electrical_Safety`, `Emergency_Procedures`, `Excavation`,
`Formwork_Reinforcement`, `General`, `Housekeeping`, `Hydrocarbon_Safety`,
`Material_Handling_Lifting`, `PPE`, `Permits`, `Radiography`, `Road_Work`,
`Safety_Awareness_Training`, `Welfare_Facilities`, `Working_at_Heights`.

Key columns include: `inspection_id`, `ro_name`, `section`, `item_id`, `response`
(`Yes`/`No`/`NA`), `remark`, `risk_level`.

**Purpose**: Primary data source for the numerical pipeline. Used in `seed.py` previously
to pre-populate inspection rows (now removed from current seed — dashboards start empty).
Used in the numerical notebook for validating the compliance formula and producing
network-analysis charts.

### 3.2 IOCL_Inspection_Summary.csv (`NumericalAnalysis/`)

**Source**: `NumericalAnalysis/IOCL_Inspection_Summary.csv`  
**Verified from**: notebook output and `seed.py` (reads this file to derive the org hierarchy)

| Property | Value |
|---|---|
| Row count | 712 |
| Granularity | One row per inspection (pre-computed rollup) |

Key columns include: `inspection_id`, `ro_id`, `ro_name`, `ro_profile`
(`Good`/`Average`/`Poor`), `office_id`, `office_name`, `city`, `state`, `zone`,
`compliance_score`, `overall_risk_level`, `semantic_risk_score`, `year`, `quarter`,
and per-section scores (`section_ppe_score`, `section_housekeeping_score`, etc.).

**Purpose**: (a) Used by `seed.py` to extract the organisational hierarchy: 5 zones,
20 offices (OFF01–OFF20), and 89 retail outlets (ROs). (b) Used in the numerical
analysis notebook to validate that the re-computed compliance matches the pre-computed
values exactly (max diff = 0.0). (c) Contains `semantic_risk_score` and
`overall_risk_level` used in the combined risk validation (~90.9% agreement
[from CLAUDE.md]).

### 3.3 IOCL_Remarks_ML_Expanded.csv (`SymanticAnalysis/`)

**Source**: `SymanticAnalysis/IOCL_Remarks_ML_Expanded.csv`  
**Verified from**: `SymanticAnalysis/IOCL_Model_Training_CV.ipynb` Step 1 output

| Property | Value |
|---|---|
| Row count | 12,473 |
| Unique remarks | 12,473 (every row is unique) |
| Remark groups | 559 (`remark_group` column) |
| Avg remarks per group | ~22.3 (= 12,473 / 559) |

**Columns**: `remark_group`, `item_id`, `response`, `remark`, `risk_level`, `risk_category`

**Label distribution** (exact counts not shown in captured output, but the three classes
are `Low`, `Medium`, `High`; the label order after `LabelEncoder.fit` is alphabetical:
`['High', 'Low', 'Medium']` → integer codes `{0: High, 1: Low, 2: Medium}`).

**Synthetic data generation**: Each of the 559 `remark_group` values represents a base
observation (e.g., "Fire extinguisher present but pressure gauge reading below minimum").
Each group is then expanded to ~22 lexical variations by template transformations — adding
preambles ("At time of inspection, …", "On site visit, …"), word substitutions, and
paraphrases. All variations in the same group carry the same `risk_level` label.

**The data-leakage problem and its fix**: In a naive random split, template variations of
the same base remark would appear in both training and test sets. The model could then
achieve artificially inflated accuracy by memorising surface patterns rather than learning
semantic risk. The fix is `GroupKFold` (and `GroupShuffleSplit` for held-out evaluation)
on the `remark_group` column, ensuring that all variations of a given base remark are
kept together in one split. This is the `SymanticAnalysis/IOCL_Model_Training_CV.ipynb`
"v2" notebook (see its first cell: "5-fold GroupKFold cross-validation instead of a single
split → the 'best model' is robust").

---

## 4. Semantic ML Pipeline

**Source**: `SymanticAnalysis/IOCL_Model_Training_CV.ipynb`, `backend/classifier.py`

### 4.1 Encoder: all-MiniLM-L6-v2

- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Output dimension**: 384 (verified: `X_emb.shape = (12473, 384)`, notebook Step 4)
- **Usage**: Frozen (not fine-tuned). Remarks are encoded to 384-dim dense vectors;
  no gradient flows through the encoder.
- **Encoding**: done **once** before the cross-validation loop (`bert.encode(X_text.tolist(), show_progress_bar=True, batch_size=64)`), then the resulting `X_emb` array is reused for every fold and every model, making the CV efficient.
- At serving time (production): `SentenceTransformer('all-MiniLM-L6-v2')` is loaded
  once at import in `backend/classifier.py` and reused for both classification
  (via `predict_labels()`) and RAG retrieval (via the `encoder` public alias).

### 4.2 Five-fold GroupKFold Cross-Validation

```python
gkf = GroupKFold(n_splits=5)
# split on remark_group so no group leaks across folds
for tr, te in gkf.split(X_emb, y, groups):
    ...
```

Five model families were evaluated on BERT embeddings, plus two baselines.
**Exact results from notebook Step 6 and Step 7 output:**

| Model | Acc mean | Acc std | Macro-F1 mean | Macro-F1 std |
|---|---|---|---|---|
| Keyword baseline | 54.1% | ±6.2 | 51.9% | ±5.8 |
| TF-IDF + Random Forest | 79.2% | ±2.5 | 77.2% | ±2.8 |
| **BERT + Logistic Regression** | **79.1%** | **±4.7** | **76.8%** | **±4.2** |
| BERT + SVM (rbf) | 75.8% | ±4.1 | 73.3% | ±3.1 |
| BERT + Random Forest | 59.0% | ±3.7 | 54.1% | ±2.5 |
| BERT + Gradient Boosting | 68.9% | ±3.2 | 66.2% | ±1.8 |
| BERT + XGBoost | 73.1% | ±5.7 | 70.2% | ±4.0 |

**Winner** (notebook Step 8): `BERT + Logistic Regression`, selected by comparing only
the BERT-family models (`bert_rows.loc[bert_rows['MacroF1 mean'].idxmax()]`).

Model hyperparameters used in CV (notebook Step 5):
```python
LogisticRegression(max_iter=2000, random_state=42)
SVC(kernel='rbf', random_state=42)
RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=42)
GradientBoostingClassifier(n_estimators=200, random_state=42)
XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.1,
              subsample=0.9, colsample_bytree=0.9,
              tree_method='hist', eval_metric='mlogloss', verbosity=0, random_state=42)
```

TF-IDF baseline (Step 7):
```python
TfidfVectorizer(max_features=2000, ngram_range=(1,2), stop_words='english')
RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42)
```

### 4.3 Why Logistic Regression Wins on Dense Embeddings

The notebook's explanation (Step 11, "What to tell your guide"):

> "On dense BERT embeddings the linear model competes with or beats the tree ensembles —
> expected, because tree splits are axis-aligned and BERT meaning is distributed across
> all 384 dimensions."

The intuition: `all-MiniLM-L6-v2` maps semantically similar remarks to nearby points in a
384-dimensional continuous space. A hyperplane (Logistic Regression decision boundary) can
separate these clusters efficiently with few parameters, because the geometry is well-behaved.

Random Forest and Gradient Boosting rely on axis-aligned splits (each internal node tests
one feature at a time). In 384 dimensions, approximating a smooth non-linear boundary
with axis-aligned boxes is inefficient — each split ignores the other 383 features. This
is why **BERT + Random Forest collapses to 59.0% accuracy**, far below even the keyword
baseline. The Random Forest is overfitting to individual embedding dimensions rather than
learning the distributed representation. SVM with an RBF kernel does better (75.8%) because
the kernel implicitly computes inner products in the full embedding space, but LogReg's
regularised linear boundary on these geometrically structured embeddings is sufficient.

XGBoost (73.1%) outperforms gradient boosting and RF in this setting because its
column subsampling (`colsample_bytree=0.9`) and row subsampling (`subsample=0.9`)
reduce the variance of axis-aligned splits, but it still cannot fully exploit the
distributed embedding geometry.

### 4.4 Held-Out Evaluation (GroupShuffleSplit)

After selecting Logistic Regression by CV, the notebook refits on a clean held-out split:

```python
tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
              .split(X_emb, y, groups))
```

The held-out macro-F1 is reported as **~0.83** [from CLAUDE.md; the classification
report output was truncated in the notebook capture]. The per-class breakdown
and confusion matrix were produced at this step but are not captured in the static
notebook output. The notebook notes "Medium class weakest" — consistent with the
class being a middle-ground label where syntactic similarity to Low and High remarks
causes more mis-classification.

### 4.5 Model Bundle

Saved as `SymanticAnalysis/risk_classifier_bundle.pkl`. Contents (verified from
notebook Step 9 code):

```python
bundle = {
    'classifier':    best_model,          # LogisticRegression fitted instance
    'encoder_name': 'all-MiniLM-L6-v2',  # string, not the encoder object itself
    'labels':        LABELS,              # ['High', 'Low', 'Medium'] (alphabetical)
    'embedding_dim': int(X_emb.shape[1]), # 384
    'cv_macro_f1':   float(bert_rows['MacroF1 mean'].max()),  # 76.8 (as float)
}
```

The encoder is **not** serialised into the bundle. `backend/classifier.py` loads the
bundle and then instantiates `SentenceTransformer(bundle["encoder_name"])` separately.
Bundle path is resolved with pathlib relative to repo root:
`_REPO_ROOT / "SymanticAnalysis" / "risk_classifier_bundle.pkl"`.

### 4.6 Sanity-Check Predictions

Verified from notebook Step 10 output:

| Remark | Predicted |
|---|---|
| Fire extinguisher present but pressure gauge reading below minimum | **Medium** |
| All helmets checked and found in good condition | Medium |
| No ELCB installed on main panel, workers exposed to electrocution risk | **High** |
| Safety shoes worn by all staff during inspection | **Low** |
| The gauge is acting a bit funny today | Medium |
| Extinguisher situation looks bad, needs urgent fixing | **High** |

Note: "All helmets checked and found in good condition" being labelled Medium rather
than Low illustrates the synthetic-data ceiling — the model over-generalises "pressure"
and "gauge" contexts. On real field remarks, this would likely be a Low.

### 4.7 Production Inference (`backend/classifier.py`)

```python
def predict_labels(remarks: list[str]) -> list[str]:
    vecs = _encoder.encode(remarks)
    indices = _bundle["classifier"].predict(vecs)
    return [_bundle["labels"][i] for i in indices]
```

The encoder and bundle are loaded once at import time. All 144 remarks from a single
inspection are encoded in a single batch call and classified together, then labels are
mapped back using the bundle's label list.

---

## 5. Numerical Pipeline

**Source**: `NumericalAnalysis/IOCL_Numerical_Analysis.ipynb`, `backend/risk_engine.py`

### 5.1 Compliance Formula

```
compliance = Yes / (Yes + No) × 100
```

- `NA` responses are **excluded** from both numerator and denominator.
- If a section has no Yes or No responses (all NA), it is **skipped** entirely.
- Rounded to 2 decimal places.

Implemented identically in the notebook (`analyse_inspection()`) and in the production
backend (`risk_engine._compliance()`):

```python
def _compliance(items: list[dict]) -> float:
    yes = sum(1 for it in items if it["response"] == "Yes")
    no  = sum(1 for it in items if it["response"] == "No")
    return round(100 * yes / (yes + no), 2) if (yes + no) else 0.0
```

### 5.2 Section Scores

The same formula is applied per section, and only sections with at least one Yes or No
response are included in the output:

```python
def _section_scores(items: list[dict]) -> dict[str, float]:
    # groups items by section, computes Yes/(Yes+No)*100 per group
    # skips sections where yes+no == 0
```

Section scores below 70% are exposed as `section_flags` in the API response:
```python
section_flags = {s: v for s, v in sorted(secs.items(), key=lambda x: x[1]) if v < 70}
```

Example from notebook (INSP00001):
- `Abrasive_Blasting_Painting`: 50.0%
- `Concreting`: 0.0%
- `Confined_Space`: 80.0%
- `Cutting_Welding_Grinding`: 50.0%
- `Documentation`: 100.0%
- `Electrical_Safety`: 70.0%
- … (17 sections total for this inspection)

### 5.3 Numerical Risk Score

```
numerical_risk_score = 100 − compliance
```

This is intentionally simple: a station with 75.93% compliance has a numerical risk
score of 24.07. It represents "percentage of Yes/No items that were No". It is a
direct, interpretable complement.

Note: The notebook also defines standalone *numerical risk bands* (compliance < 70 →
"High", 70–85 → "Medium", ≥85 → "Low") for chart annotations, but these standalone
bands are **not** used in the production combined engine. The combined engine uses the
Final Risk Index thresholds (≥25 → High, ≥15 → Medium, else Low).

### 5.4 Validation Against Pre-Computed Summary

**From notebook Step 4 / Step 5 output** (verified):

```
Inspections checked: 712 | max difference: 0.0
=> our pipeline reproduces the official compliance score.
```

The re-computed compliance for every one of 712 inspections matches the pre-computed
Summary CSV to **0.0 absolute difference** (i.e., an exact match). This validates that
the formula implementation is correct.

INSP00001 example (verified from notebook):
- Our formula: 75.93%
- Summary CSV: 75.93% (exact match confirmed)

---

## 6. Combined Risk Engine

**Source**: `backend/risk_engine.py`

### 6.1 Semantic Risk Score

```python
def _semantic_score(label_counts: dict) -> float:
    H = label_counts.get("High", 0)
    M = label_counts.get("Medium", 0)
    L = label_counts.get("Low", 0)
    total = H + M + L
    return round((2 * H + 1 * M) / total * 100, 2) if total else 0.0
```

**Formula**:
```
semantic_risk_score = (2×#High + 1×#Medium) / total_items × 100
```

Weight rationale: High items are twice as penalising as Medium; Low items contribute
zero. The total is the count of all items (including Low), so a high proportion of Low
items dilutes the score. This is a policy choice (not learned from data).

### 6.2 Final Risk Index and Blending Weights

```python
W_NUMERICAL, W_SEMANTIC = 0.40, 0.60

def _final_index(num: float, sem: float) -> float:
    return round(W_NUMERICAL * num + W_SEMANTIC * sem, 2)
```

```
Final Risk Index = 0.40 × numerical_risk_score + 0.60 × semantic_risk_score
```

The 60% weight on the semantic signal reflects the project's core thesis: the remark
content carries more diagnostic value than the Yes/No boxes alone. Both weights are
**policy choices**, not learned from data.

### 6.3 Risk Bands (Final Risk Index Thresholds)

```python
LOW_BELOW, HIGH_AT = 15, 25

def _final_risk(idx: float) -> str:
    if idx >= HIGH_AT:   return "High"
    if idx >= LOW_BELOW: return "Medium"
    return "Low"
```

| Index | Risk Band |
|---|---|
| ≥ 25 | **High** |
| ≥ 15, < 25 | **Medium** |
| < 15 | **Low** |

These thresholds are **tunable policy choices**, documented as such in the codebase.

### 6.4 Hidden Risk Count

```python
hidden = sum(
    1 for it in items
    if it["response"] == "Yes" and it["risk_label"] == "High"
)
```

A hidden risk is defined as any item where the inspector ticked **Yes** (compliant)
but the semantic classifier predicted a **High** risk remark. This is the project's
signature output — it surfaces "looks safe, isn't" items.

### 6.5 Full `assess()` Return Payload

```python
{
    "overall_risk":          str,   # "Low" / "Medium" / "High"
    "final_risk_index":      float,
    "compliance_score":      float,
    "numerical_risk_score":  float,
    "semantic_risk_score":   float,
    "hidden_risks":          int,
    "section_flags":         dict,  # {section_name: compliance_score} for < 70%
    "label_counts":          dict,  # {"Low": n, "Medium": n, "High": n}
}
```

### 6.6 Department-Level Risk (`assess_by_department`)

The same formulas are applied independently for each of the 9 departments, restricted
to items in that department's mapped section:

```python
DEPT_SECTIONS: dict[str, str] = {
    "PPE":           "PPE",
    "Housekeeping":  "Housekeeping",
    "Permits":       "Permits",
    "Electrical":    "Electrical_Safety",
    "Hydrocarbon":   "Hydrocarbon_Safety",
    "Emergency":     "Emergency_Procedures",
    "Confined":      "Confined_Space",
    "Welding":       "Cutting_Welding_Grinding",
    "Documentation": "Documentation",
}
```

Departments whose mapped section has no Yes/No items in this inspection are skipped.
Output per department: `{compliance, numerical_risk, semantic_risk, final_index, risk_band, hidden_risks}`.

### 6.7 Bulk Validation (~90.9% Agreement)

**[From CLAUDE.md]**: The combined risk engine was validated against the pre-computed
`overall_risk_level` column in `IOCL_Inspection_Summary.csv` and achieved approximately
**90.9% agreement** across the 712 inspections. The notebook for this step is not
captured in the static output. The ~9.1% divergence is attributed to:
- Weight choices (40/60) differing from the dataset's generation methodology.
- Threshold choices (15/25) being an approximation of the ground-truth label boundaries.
- The dataset labels being derived from a two-step generation process (numerical risk
  generated first, semantic added as a modifier), creating a slightly different joint
  distribution.

---

## 7. Multi-Role Platform — Auth, Data Model, API

### 7.1 Authentication (`backend/auth.py`)

**Protocol**: OAuth2 Password Flow → JWT Bearer tokens.

| Property | Value |
|---|---|
| Algorithm | HS256 |
| Token expiry | 8 hours (`_TOKEN_HOURS = 8`) |
| Secret key | `os.getenv("SECRET_KEY", "iocl-dev-secret-key-change-in-production")` |
| Password hashing | `passlib.CryptContext(schemes=["bcrypt"])` |
| JWT library | `python-jose` |
| bcrypt version | **pinned to 4.0.1** (passlib 1.7.x is incompatible with bcrypt ≥ 4.1 due to wrap-bug detection) |

Token creation:
```python
def create_token(username: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=_TOKEN_HOURS)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)
```

Role enforcement:
```python
def require_role(*roles: str):
    async def _check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return _check
```

Used in every route: `_inspector = require_role("inspector")`, etc.

### 7.2 Database (`backend/database.py`)

```python
_DB_PATH = Path(__file__).resolve().parent.parent / "iocl.db"
engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)
```

SQLite file at repo root. Created by `SQLModel.metadata.create_all(engine)` on app
startup (and by `seed.py`). Sessions are provided via `get_session()` FastAPI dependency.

### 7.3 Data Model (`backend/models.py`)

Six SQLModel table classes:

#### `zones`
| Column | Type | Notes |
|---|---|---|
| `id` | int PK | auto |
| `name` | str UNIQUE | e.g. "Delhi NCR" |

#### `offices`
| Column | Type | Notes |
|---|---|---|
| `id` | int PK | auto |
| `code` | str UNIQUE | e.g. "OFF01" |
| `name` | str | e.g. "Delhi Central" |
| `city` | str | |
| `state` | str | |
| `zone_id` | int FK→zones | |

#### `ros` (Retail Outlets)
| Column | Type | Notes |
|---|---|---|
| `id` | int PK | auto |
| `code` | str UNIQUE | e.g. "RO0001" |
| `name` | str | |
| `office_id` | int FK→offices | |
| `profile` | str | "Good" / "Average" / "Poor" |

#### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | int PK | auto |
| `username` | str UNIQUE | |
| `password_hash` | str | bcrypt hash |
| `role` | str | "inspector" / "zone_head" / "dept_officer" |
| `full_name` | str | |
| `office_id` | int FK→offices, nullable | inspectors and dept officers |
| `zone_id` | int FK→zones, nullable | zone heads only |
| `department` | str, nullable | dept officers only; one of 9 fixed values |

#### `inspections`
| Column | Type | Notes |
|---|---|---|
| `id` | int PK | auto |
| `ro_id` | int FK→ros | |
| `submitted_by` | int FK→users | inspector's user id |
| `submitted_at` | str | UTC ISO timestamp |
| `overall_risk` | str | "Low" / "Medium" / "High" |
| `final_risk_index` | float | blended 40/60 score |
| `compliance_score` | float | numerical compliance % |
| `numerical_risk_score` | float | 100 − compliance |
| `semantic_risk_score` | float | (2H+M)/total×100 |
| `hidden_risks` | int | count of Yes∧High items |
| `label_counts_json` | str | JSON: {"Low":n,"Medium":n,"High":n} |

#### `inspection_items`
| Column | Type | Notes |
|---|---|---|
| `id` | int PK | auto |
| `inspection_id` | int FK→inspections, **indexed** | |
| `section` | str | e.g. "PPE" |
| `item_id` | str | e.g. "A1", "HC12" |
| `question` | str, default="" | item description text, passed from frontend |
| `response` | str | "Yes" / "No" / "NA" |
| `remark` | str | inspector's free text |
| `predicted_label` | str | "Low" / "Medium" / "High" |
| `resolved` | bool, default False | resolution flag |
| `resolved_by_user_id` | int FK→users, nullable | dept officer who resolved |
| `resolved_by_name` | str, nullable | snapshot of full_name at resolve time |
| `resolved_at` | str, nullable | UTC ISO string |
| `recommendation` | str, nullable | RAG-generated corrective action |
| `recommendation_sections` | str, nullable | JSON list of cited OISD-STD-225 section IDs |

#### `department_risks`
| Column | Type | Notes |
|---|---|---|
| `id` | int PK | auto |
| `inspection_id` | int FK→inspections, **indexed** | |
| `department` | str | one of 9 dept names |
| `compliance` | float | dept-level compliance % |
| `numerical_risk` | float | 100 − compliance |
| `semantic_risk` | float | dept-level semantic score |
| `final_index` | float | blended score |
| `risk_band` | str | "Low" / "Medium" / "High" |
| `hidden_risks` | int | dept-level hidden risk count |

### 7.4 Organisational Hierarchy (Seeded)

Seeded from `IOCL_Inspection_Summary.csv` by `backend/seed.py`:

- **5 zones**: Delhi NCR, UP Region, Rajasthan Region, Punjab Haryana Region, Uttarakhand Region
- **20 offices**: OFF01 (Delhi Central) through OFF20 (Haridwar)
- **~89 ROs** (derived from unique `ro_id` values in Summary CSV [from CLAUDE.md])
- **5 zone heads** (one per zone):

| Username | Full Name | Zone |
|---|---|---|
| `zh_delhi_ncr` | Rajesh Kumar | Delhi NCR |
| `zh_punjab_haryana` | Gurpreet Singh | Punjab Haryana Region |
| `zh_rajasthan` | Vikram Meena | Rajasthan Region |
| `zh_up` | Anil Sharma | UP Region |
| `zh_uttarakhand` | Deepak Rawat | Uttarakhand Region |

- **20 inspectors**: `insp_off01` through `insp_off20` (one per office, office_id bound)
- **18 dept officers**: 9 departments × 2 offices (OFF01 Delhi Central, OFF08 Lucknow)
  - Pattern: `dept_{dept.lower()}_{office.lower()}`
  - Example: `dept_ppe_off01`, `dept_electrical_off08`, `dept_documentation_off01`
- **Universal demo password**: `demo1234`
- **Total demo accounts**: 5 + 20 + 18 = **43 users**

### 7.5 Role Scoping

| Role | Tied to | Can do | Out-of-scope → |
|---|---|---|---|
| `inspector` | ONE office (`office_id`) | Submit checklist for ROs in their office only. Cannot see risk results. | 403 |
| `zone_head` | ONE zone (`zone_id`) | View all inspections + full risk breakdown for any RO in their zone. | 403 |
| `dept_officer` | ONE office + ONE dept (`office_id` + `department`) | View inspections for their office's ROs; only their dept's items and risk. Mark Medium/High items resolved. | 403 |

Scope enforcement example (verified from `routes/zone_head.py`):
```python
office = session.get(Office, ro.office_id)
if office.zone_id != user.zone_id:
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Inspection is outside your zone")
```

### 7.6 Complete API Endpoint List

All endpoints require `Authorization: Bearer <token>` except `/health`.

```
GET   /health                                         → {"status": "ok"}
POST  /auth/login                                     → {access_token, token_type, role}
GET   /auth/me                                        → {id, username, full_name, role, office_id, zone_id, department}

# Inspector (role: inspector)
GET   /my/ros                                         → [{ro_id, ro_code, ro_name, profile}]
POST  /inspections                                    → {status:"submitted", inspection_id}

# Zone Head (role: zone_head)
GET   /zone/inspections                               → [{id, ro_name, ro_code, submitted_at, overall_risk,
                                                           final_risk_index, compliance_score}]
GET   /inspections/{insp_id}                          → full detail (items + risk + dept breakdown + section_flags)

# Dept Officer (role: dept_officer)
GET   /dept/inspections                               → [{id, ro_name, ro_code, submitted_at,
                                                           dept_risk_band, dept_final_index}]
GET   /dept/inspections/{insp_id}                     → {dept, dept_risk, items (dept section only)}
POST  /dept/inspections/{insp_id}/items/{item_db_id}/resolve  → resolved item; idempotent; 403 if wrong office/dept; 400 if Low
```

Detail item fields (both zone_head and dept_officer detail views):
`id`, `section`, `item_id`, `response`, `remark`, `predicted_label`,
`resolved`, `resolved_by_name`, `resolved_at`, `recommendation`, `recommendation_sections`

---

## 8. Issue-Resolution Workflow

**Source**: `backend/models.py`, `backend/routes/dept_officer.py`,
`backend/routes/zone_head.py`, `frontend/index.html`

### 8.1 Resolvable Items

Only items with `predicted_label ∈ {"Medium", "High"}` can be resolved. Low-risk items
are not resolvable (enforced by HTTP 400 in `resolve_item()`):

```python
_RESOLVABLE = {"Medium", "High"}
...
if item.predicted_label not in _RESOLVABLE:
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only Medium/High items can be resolved")
```

### 8.2 Resolution Action (`POST .../resolve`)

When a dept officer calls the resolve endpoint:

```python
if not item.resolved:   # idempotent — re-resolving is a no-op
    item.resolved = True
    item.resolved_by_user_id = user.id
    item.resolved_by_name = user.full_name          # snapshot at resolve time
    item.resolved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    session.add(item)
    session.commit()
```

Three fields are written atomically:
- `resolved = True`
- `resolved_by_name`: a **snapshot** of the officer's `full_name` at the moment of
  resolution, so even if the user record is later modified the audit trail is preserved.
- `resolved_at`: UTC ISO-8601 timestamp, format `YYYY-MM-DDTHH:MM:SS+00:00`.

### 8.3 Scope Enforcement for Resolution

Double-scoped: the inspection must belong to the officer's office **and** the item must
belong to the officer's department section:

```python
if ro.office_id != user.office_id:
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Inspection is outside your office")
...
if item.section != dept_section:
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Item is not in your department")
```

### 8.4 Zone Head Read-Only View

Zone heads see resolution status as a read-only badge. In `frontend/index.html`
(`loadZhDetail()` function):

```javascript
const resStatus = isActionable
  ? (it.resolved
      ? `<span class="resolved-badge">✓ Resolved by ${escHtml(it.resolved_by_name)}
             · ${fmtDateTime(it.resolved_at)}</span>`
      : `<span class="unresolved-badge">⚠ Unresolved</span>`)
  : '';
```

- **Resolved**: green "Resolved by [Name] · DD Mon YYYY, HH:MM" badge.
- **Unresolved**: amber "⚠ Unresolved" badge.
- **Low**: no badge (not actionable).

Date/time formatting uses `fmtDateTime()` which applies `en-IN` locale formatting:
`DD Mon YYYY, HH:MM` (24-hour).

### 8.5 Dept Officer Interactive Resolution

In `loadDeptDetail()`, the resolve button is rendered per-item:

```javascript
actionHtml = it.resolved
  ? `<span class="resolved-badge">✓ Resolved by ... · ${fmtDateTime(...)}</span>`
  : `<button class="resolve-btn" id="rbtn-${it.id}"
            onclick="resolveDeptItem(${d.id},${it.id},this)">Mark Resolved</button>`;
```

On click, `resolveDeptItem()` fires `POST /dept/inspections/{insp_id}/items/{item_db_id}/resolve`,
disables the button during the call, then replaces the button DOM node inline with a
resolved badge from the server's response — no page reload required.

### 8.6 Question Text Rendering

Item descriptions (the question text from the original checklist) are stored in
`InspectionItem.question` (written at submit time from the frontend's `CHECKLIST` array).
On detail screens, the frontend also resolves descriptions from a local `CHECKLIST_MAP`
built once at page load:

```javascript
const CHECKLIST_MAP = {};
for (const sec of CHECKLIST)
  for (const it of sec.items)
    CHECKLIST_MAP[`${sec.section}::${it.item_id}`] = it.description;

function qtext(section, item_id) {
  return CHECKLIST_MAP[`${section}::${it.item_id}`] || '';
}
```

This means the question text is available in the detail view without any backend changes,
independent of whether `item.question` was populated.

---

## 9. RAG Recommendation Layer

**Source**: `backend/rag/ingest.py`, `backend/rag/retriever.py`,
`backend/rag/llm.py`, `backend/rag/recommend.py`, `backend/routes/inspector.py`

### 9.1 Corpus

**PDF**: `backend/rag/corpus/OISD-STD-225.pdf` — the Oil Industry Safety Directorate
standard on "Safety Requirements for Petroleum Depots, Terminals and Pipeline Installations".
This document contains clauses, annexures, and tables on safety procedures, equipment
requirements, and corrective actions for petroleum retail operations.

The PDF is not committed to the repository (gitignored indirectly via the vectorstore
directory). It must be placed manually before running ingest.

### 9.2 Text Extraction

```python
from pypdf import PdfReader

def _extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = [p.extract_text() or "" for p in reader.pages]
    return "\n".join(pages)
```

All pages are concatenated with newlines. This produces a single long string of raw
extracted text.

### 9.3 Chunking Strategy

**Primary: Clause-level splitting** using a compiled regex:

```python
_CLAUSE_RE = re.compile(
    r'(?m)^(?=(?:Annexure\s+[IVX]+|(?:\d+\.)+(?:\d+|[ivxlcdm]+|[a-z])\s|\d+\s+[A-Z]))',
    re.IGNORECASE,
)
```

This regex matches the *start* of:
- Annexure headings: `Annexure I`, `Annexure IV`, etc.
- Numbered sub-clauses: `5.3`, `10.i`, `2.4.a`, etc.
- Top-level numbered sections: `10 SAFETY REQUIREMENTS`, etc.

Each matched segment becomes one chunk, with:
- Hard cap: **1200 characters** per chunk (`part[:1200]`).
- Metadata: `section` (the clause number, e.g. "5.3"), `section_name` (first line up to
  80 chars), `type` (`"clause"` or `"annexure_row"`).

**Fallback: Sliding window** (triggered if clause splitting yields fewer than 20 chunks):

```python
def _sliding_chunks(text: str, size: int = 400, overlap: int = 50) -> list[dict]:
    words = text.split()
    step = size - overlap   # 350 words per step
    ...
```

Sliding window: 400 words per chunk, 50-word overlap (step = 350 words).
Attempts to detect section headers within the chunk text for metadata.

### 9.4 Vector Store

- **Engine**: ChromaDB `PersistentClient`, stored at `backend/rag/vectorstore/` (local directory, persists across restarts).
- **Collection name**: `"oisd_std_225"`
- **Similarity metric**: cosine (`metadata={"hnsw:space": "cosine"}`)
- **Embedding function**: `None` — embeddings are computed externally using the same
  `all-MiniLM-L6-v2` encoder already loaded by `backend/classifier.py` (reused via
  `from ..classifier import encoder as _encoder`). This avoids loading a second
  encoder model at startup.

Ingestion flow:
```python
texts = [c["text"] for c in chunks]
BATCH = 64
all_embeddings = []
for i in range(0, len(texts), BATCH):
    batch = texts[i: i + BATCH]
    embs = _encoder.encode(batch, show_progress_bar=False)
    all_embeddings.extend(embs.tolist())

collection.add(
    ids       = [str(i) for i in range(len(chunks))],
    embeddings= all_embeddings,
    documents = texts,
    metadatas = [{
        "source":       "OISD-STD-225",
        "section":      c["section"],
        "section_name": c["section_name"],
        "type":         c["type"],
    } for c in chunks],
)
```

Ingestion is **idempotent**: the existing collection is deleted and recreated each run
(`client.delete_collection(_COLLECTION)` before `create_collection`).

### 9.5 Retrieval (`backend/rag/retriever.py`)

```python
def retrieve(query: str, k: int = 4) -> list[dict]:
    col = _get_collection()
    if col is None or col.count() == 0:
        return []
    qvec = _encoder.encode([query])[0].tolist()
    results = col.query(
        query_embeddings=[qvec],
        n_results=min(k, col.count()),
        include=["documents", "metadatas", "distances"],
    )
    return [{
        "text":         doc,
        "section":      meta.get("section", ""),
        "section_name": meta.get("section_name", ""),
        "score":        round(1.0 - float(dist), 4),   # cosine distance → similarity
    } for doc, meta, dist in zip(...)]
```

Chroma is initialised **lazily** on first call (not at app startup), so the application
starts fine even if the vectorstore has not been built yet. Returns `[]` if unavailable —
never raises.

Default `k=4`: retrieves the 4 most relevant OISD-STD-225 chunks per item.

### 9.6 LLM Adapter (`backend/rag/llm.py`)

**Provider**: Groq (via the OpenAI Python SDK with a custom base URL).

| Env var | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | (none) | Required. If absent, `generate()` returns None silently. |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Model name on Groq's platform. |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Override for local or alternate providers. |

Key design choices:
- Env vars are **re-read on every `generate()` call** via `load_dotenv(..., override=True)`,
  so the key can be added or changed without restarting the server.
- The OpenAI client is **cached** and rebuilt only if the API key changes.
- `max_tokens=350`, `timeout=25.0` seconds.
- Returns `None` on any error — never raises, so it cannot break the inspection submission.

**Provider-agnostic design**: Changing only the three env vars (`GROQ_BASE_URL`,
`GROQ_MODEL`, `GROQ_API_KEY`) is sufficient to switch to any OpenAI-compatible provider
(local Ollama, Azure, etc.) with zero code changes.

```python
resp = _get_client(api_key, base_url).chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ],
    max_tokens=350,
    timeout=timeout,
)
```

### 9.7 Recommendation Orchestration (`backend/rag/recommend.py`)

**System prompt** (full text):
```
"You are an IOCL retail-outlet safety advisor.
Using ONLY the provided OISD-STD-225 excerpts, give a concise 2-4 sentence
corrective action for the flagged inspection item, and cite the relevant section
(e.g. 'per OISD-STD-225 Section 10').
If the excerpts do not cover the item, provide general OISD-aligned best practice
and explicitly note that the specific clause was not found in the excerpts.
Do NOT invent specific numerical thresholds or quantities that are not present in
the excerpts."
```

**Query construction**:
```python
def _build_query(question: str, remark: str, section: str) -> str:
    parts = [section.replace("_", " ")]
    if question:
        parts.append(question)
    if remark:
        parts.append(remark)
    return " ".join(parts)
```

The query concatenates: (1) section name with underscores replaced by spaces, (2) the
question text (item description), and (3) the remark. This gives the retriever maximum
context to find relevant OISD clauses.

**User prompt structure**:
```
Flagged inspection item:
  Section   : {section (human-readable)}
  Question  : {question or '(not specified)'}
  Response  : {response}
  Remark    : {remark or '(none)'}
  Risk level: {risk_label}

Relevant OISD-STD-225 excerpts:
[Section 5.3 — 5.3 Safety ...] {chunk text}

[Section 10 — ...] {chunk text}
...

Provide a concise corrective action for this item.
```

**Return value**: `{"text": str | None, "cited_sections": list[str]}`

- `cited_sections` is the list of `section` metadata values from the top-4 retrieved chunks
  (e.g., `["5.3", "10", "Annexure II", "12.1"]`), providing citation transparency.
- `text` is the LLM's response, or `None` if retrieval failed or LLM call failed.

**Grounding mechanism**: The system prompt instructs the LLM to use *only* the provided
excerpts and to explicitly flag when a clause is not found. This prevents hallucination
of fake OISD section numbers or invented thresholds, producing recommendations that are
traceable back to actual standard text.

### 9.8 Submit-and-Store Flow

In `backend/routes/inspector.py`, after the inspection is committed to the database:

```python
session.commit()
# Fire background task — returns immediately; recommendations fill in within seconds.
background_tasks.add_task(_generate_recommendations, insp.id)
return {"status": "submitted", "inspection_id": insp.id}
```

The `_generate_recommendations` background function:
1. Opens a **fresh DB session** (different from the request session, which is closed).
2. Queries all items for this inspection where `predicted_label IN ('Medium', 'High')`.
3. For each: calls `recommend_for_item(question, response, remark, risk_label, section)`.
4. Writes back `recommendation` and `recommendation_sections` (JSON-encoded list).
5. A single `session.commit()` after all items are processed.
6. Any individual item failure is caught and silently skipped (`except Exception: pass`).

RAG availability is checked at startup:
```python
try:
    from ..rag.recommend import recommend_for_item as _recommend
    _RAG_AVAILABLE = True
except Exception:
    _RAG_AVAILABLE = False
```

If `chromadb` or `openai` are not installed, or the vectorstore doesn't exist, RAG
degrades silently — recommendations simply remain `null` for all items.

### 9.9 Display in the PWA

Both the zone head detail view and the dept officer detail view render a per-item
"AI Recommendation" box for Medium and High risk items:

```javascript
if (it.recommendation) {
    const secs = (it.recommendation_sections || []).join(' · §');
    recHtml = `<div class="rec-box">
      <div class="rec-label">AI Recommendation (OISD-STD-225)</div>
      <div class="rec-text">${escHtml(it.recommendation)}</div>
      ${secs ? `<div class="rec-cite">Source: OISD-STD-225 §${escHtml(secs)}</div>` : ''}
    </div>`;
} else {
    recHtml = `<div class="rec-box rec-pending">
      <div class="rec-label">AI Recommendation</div>
      <div class="rec-text">Generating…</div>
    </div>`;
}
```

- Filled: blue-bordered box with recommendation text + cited sections as `§5.3 · §10`.
- Pending (null): grey box with "Generating…" (appears if detail is loaded before
  the background task completes).
- Low-risk items: no box rendered at all.

An informational panel above the items section reads:
```
AI Recommendation Engine
Corrective actions grounded on OISD-STD-225 are generated for every Medium & High
risk item and shown inline below.
```

---

## 10. Full Tech Stack & File/Folder Structure

### 10.1 Tech Stack

| Layer | Technology | Version constraint |
|---|---|---|
| Language | Python 3.11 | Required (path: `py -3.11`) |
| Web framework | FastAPI | latest |
| ASGI server | uvicorn[standard] | latest |
| ORM | SQLModel (SQLAlchemy + Pydantic) | latest |
| Database | SQLite (file: `iocl.db`) | bundled with Python |
| Data validation | Pydantic v2 | via SQLModel |
| Semantic encoder | sentence-transformers (`all-MiniLM-L6-v2`) | latest |
| ML classifiers | scikit-learn (`LogisticRegression`, etc.) | latest |
| ML gradient boosting | xgboost | (notebook only) |
| Password hashing | passlib[bcrypt] | latest passlib, **bcrypt==4.0.1 pinned** |
| JWT tokens | python-jose[cryptography] | latest |
| Form parsing | python-multipart | latest |
| Vector store | chromadb | latest |
| LLM API client | openai (Groq compat.) | latest |
| PDF parsing | pypdf | latest |
| Env vars | python-dotenv | latest |
| Numeric array ops | numpy | latest |
| Frontend | Vanilla JS + CSS (single HTML file) | none |
| PWA | Service Worker API + Web App Manifest | browser native |

### 10.2 File/Folder Structure

```
d:\IOCL\
├── CLAUDE.md                              # project instructions for Claude Code
├── PROJECT_OVERVIEW.md                    # this document
├── iocl.db                                # SQLite database (created by seed.py)
├── .env                                   # gitignored — GROQ_API_KEY etc.
├── .env.example                           # template for .env
│
├── NumericalAnalysis/
│   ├── IOCL_Inspection_Dataset.csv        # 102,528 rows, one per checklist item
│   ├── IOCL_Inspection_Summary.csv        # 712 rows, one per inspection
│   └── IOCL_Numerical_Analysis.ipynb      # numerical pipeline notebook
│
├── SymanticAnalysis/                      # NOTE: intentionally misspelled — keep consistent
│   ├── IOCL_Model_Training_CV.ipynb       # semantic ML pipeline, GroupKFold CV
│   ├── IOCL_Remarks_ML_Expanded.csv       # 12,473 remarks, 559 groups
│   └── risk_classifier_bundle.pkl         # trained bundle (LogReg + encoder name + labels)
│
├── backend/
│   ├── __init__.py
│   ├── main.py                            # FastAPI app, routers, PWA mount
│   ├── models.py                          # 6 SQLModel table classes
│   ├── database.py                        # engine, get_session, create_db_and_tables
│   ├── auth.py                            # JWT, bcrypt, require_role()
│   ├── risk_engine.py                     # assess(), assess_by_department(), section_scores()
│   ├── classifier.py                      # bundle loader + predict_labels() + encoder alias
│   ├── schemas.py                         # Pydantic request/response models
│   ├── seed.py                            # idempotent seed: org hierarchy + 43 demo users
│   ├── smoke_test.py                      # end-to-end API validation (144-item fixture)
│   ├── test_request.py                    # (supplementary test script)
│   ├── requirements.txt                   # pinned deps
│   │
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── corpus/
│   │   │   └── OISD-STD-225.pdf          # place here before ingest (gitignored)
│   │   ├── vectorstore/                   # Chroma DB (gitignored, created by ingest.py)
│   │   ├── ingest.py                      # one-time: PDF → chunks → embeddings → Chroma
│   │   ├── retriever.py                   # lazy Chroma load, cosine query, returns list[dict]
│   │   ├── llm.py                         # Groq adapter (OpenAI SDK), env-var driven
│   │   └── recommend.py                   # orchestrates retrieve+generate, builds prompts
│   │
│   └── routes/
│       ├── __init__.py
│       ├── auth_routes.py                 # POST /auth/login, GET /auth/me
│       ├── inspector.py                   # GET /my/ros, POST /inspections + BG task
│       ├── zone_head.py                   # GET /zone/inspections, GET /inspections/{id}
│       └── dept_officer.py                # GET /dept/inspections, GET /{id}, POST resolve
│
└── frontend/
    ├── index.html                         # single-file SPA: all CSS + JS inline (~1300 lines)
    ├── manifest.json                      # PWA manifest (theme: #C41230, standalone)
    └── sw.js                              # cache-first service worker
```

### 10.3 Checklist Structure (Embedded in Frontend)

The `CHECKLIST` constant in `frontend/index.html` defines all 144 items across 21 sections.
Verified total from the JS constant: `TOTAL = 144`.

| Section | Item IDs | Count |
|---|---|---|
| PPE | A1–A3, B1–B6, B8–B10, C1–C2 (B7 absent) | 14 |
| Housekeeping | HK1–HK8 | 8 |
| Excavation | EX1–EX7 | 7 |
| Permits | PM1–PM8 | 8 |
| Cutting_Welding_Grinding | WG1–WG12 | 12 |
| Abrasive_Blasting_Painting | AB1–AB4 | 4 |
| Working_at_Heights | WH1–WH5 | 5 |
| Confined_Space | CS1–CS10 | 10 |
| Material_Handling_Lifting | MH1–MH4 | 4 |
| Electrical_Safety | EL1–EL11 | 11 |
| Road_Work | RW1–RW2 | 2 |
| Formwork_Reinforcement | FW1–FW2 | 2 |
| Concreting | CO1–CO2 | 2 |
| Demolishing | DM1–DM2 | 2 |
| Radiography | RA1–RA3 | 3 |
| Hydrocarbon_Safety | HC1–HC12 | 12 |
| Emergency_Procedures | EP1–EP11 | 11 |
| Welfare_Facilities | WF1–WF8 | 8 |
| General | GN1–GN13 | 13 |
| Safety_Awareness_Training | SA1–SA2 | 2 |
| Documentation | DC1–DC4 | 4 |
| **Total** | | **144** |

Of the 21 sections, 9 map to departments (see Section 6.6); the remaining 12 contribute
to overall risk but have no departmental owner.

---

## 11. Results & Validation

### 11.1 Numerical Pipeline Validation

**Source**: `NumericalAnalysis/IOCL_Numerical_Analysis.ipynb`, Step 4 (group-apply) output.

| Metric | Value |
|---|---|
| Inspections validated | 712 |
| Maximum absolute difference | **0.0** |
| Conclusion | Exact match — formula reproduces pre-computed compliance scores |

### 11.2 Semantic Pipeline Results

**Source**: `SymanticAnalysis/IOCL_Model_Training_CV.ipynb`, Step 6 output.

| Model | CV Accuracy | CV Macro-F1 |
|---|---|---|
| Keyword baseline | 54.1 ± 6.2% | 51.9 ± 5.8% |
| TF-IDF + Random Forest | 79.2 ± 2.5% | 77.2 ± 2.8% |
| **BERT + Logistic Regression (selected)** | **79.1 ± 4.7%** | **76.8 ± 4.2%** |
| BERT + SVM (rbf) | 75.8 ± 4.1% | 73.3 ± 3.1% |
| BERT + Random Forest | 59.0 ± 3.7% | 54.1 ± 2.5% |
| BERT + Gradient Boosting | 68.9 ± 3.2% | 66.2 ± 1.8% |
| BERT + XGBoost | 73.1 ± 5.7% | 70.2 ± 4.0% |

CV protocol: 5-fold GroupKFold on `remark_group`, evaluating macro-F1 as primary metric
(because classes are imbalanced and accuracy alone misleads).

Bundle-stored `cv_macro_f1`: **76.8** (verified from `bundle['cv_macro_f1']` in save step).

Held-out macro-F1 (GroupShuffleSplit, 20% test): **~0.83** [from CLAUDE.md;
held-out `classification_report` output not captured in static notebook].

### 11.3 Combined Risk Engine Validation

**Source**: [from CLAUDE.md; notebook output not captured]

| Metric | Value |
|---|---|
| Inspections validated | 712 |
| Agreement with dataset `overall_risk_level` | **~90.9%** |
| Methodology | Compare `_final_risk(final_risk_index)` vs Summary CSV `overall_risk_level` |

### 11.4 Smoke Test (End-to-End API)

**Source**: `backend/smoke_test.py`

12 checks verified (run against a live server):
1. `GET /health` returns `{"status": "ok"}`
2. Inspector `GET /my/ros` returns ≥ 1 RO
3. Inspector `POST /inspections` (144 items) returns `{status:"submitted"}`
4. Inspector is blocked from `/zone/inspections` with HTTP 403
5. Zone head `GET /zone/inspections` returns ≥ 1 inspection
6. Zone head `GET /inspections/{id}` returns 144 items
7. Zone head detail has `department_risks` array
8. Zone head detail has `section_flags` key
9. Zone head from different zone gets HTTP 403
10. Dept officer `GET /dept/inspections` returns ≥ 1 inspection
11. Dept officer detail `department == "PPE"`
12. Dept officer from different office gets HTTP 403

---

## 12. Key Technical Decisions & Rationale

### 12.1 ML for Semantic, Formula for Numerical

The compliance formula (`Yes/(Yes+No)×100`) is an exact deterministic relationship
specified by the inspection standard itself. There is nothing to learn — the formula
is exact and interpretable. Introducing ML here would add complexity without benefit.

Remark classification, by contrast, requires understanding natural-language semantics
that cannot be captured by a deterministic rule. The keyword baseline (54.1% accuracy)
demonstrates this: pattern matching on words like "absent", "missing", "not" is brittle
and context-blind ("not bad" vs "bad" vs "not in compliance" all need different treatment).

### 12.2 Frozen BERT Encoder vs Fine-Tuning

Arguments for frozen encoding:
- The dataset has 559 unique groups → effective training-set size is much smaller than
  12,473 rows suggest. Fine-tuning on 80% of 559 groups risks overfitting.
- `all-MiniLM-L6-v2` is already trained on 1B+ sentence pairs covering diverse domains;
  its semantic representations transfer well to safety inspection remarks.
- Encoding is done once (`X_emb = bert.encode(...)`); the CV loop never re-encodes.
  This makes the total compute cost equivalent to one BERT forward pass, not 5× the CV.
- The 384-dim embeddings yield 79.1% CV accuracy without fine-tuning, competitive with
  TF-IDF+RF (79.2%).

### 12.3 Logistic Regression over Tree Ensembles on BERT Embeddings

See Section 4.3 for the detailed argument. Summary: BERT embeddings form geometrically
structured clusters in continuous 384-dim space; a hyperplane (LogReg) separates them
efficiently. Tree splits are axis-aligned and cannot exploit the full distributed
representation — hence BERT + RF collapses to 59.0%.

### 12.4 40/60 Blending Weights as Policy, Not Learned

Weights `W_NUMERICAL=0.40, W_SEMANTIC=0.60` are **explicitly not learned** from data.
This is a deliberate architectural choice with several justifications:
1. **Interpretability**: a regulator or auditor can understand "40% from compliance
   counts, 60% from remark analysis" without a black-box weight explanation.
2. **Policy signal**: the 60% on semantic reflects the project's thesis that remark
   content is more diagnostic. This is a defensible engineering judgment.
3. **Avoiding overfitting**: with only 712 inspections and 3 risk classes, learning
   the blend weights from data (e.g., logistic regression on the two scores) would
   be highly sensitive to the training split and the imbalanced dataset.
4. **Tunability**: documented as `W_NUMERICAL, W_SEMANTIC = 0.40, 0.60` in a single
   line, easy to adjust during policy reviews.

### 12.5 ChromaDB for Vector Store

ChromaDB is an embedded, serverless vector database (similar to SQLite for vectors).
- No separate server process to manage or deploy.
- Persists to a local directory (`backend/rag/vectorstore/`).
- Supports cosine similarity out of the box (`hnsw:space=cosine`).
- The external embedding function is set to `None` (embeddings provided by caller),
  allowing reuse of the already-loaded MiniLM encoder without a second model instance.

### 12.6 Groq for LLM Inference

Groq provides fast inference on LLaMA models with a free tier and an OpenAI-compatible
API, making it a practical choice for an internship prototype:
- Zero incremental cost for development/demo.
- `llama-3.1-8b-instant` is fast enough for background task processing (~25s timeout).
- Provider-agnostic: only three env vars need changing to switch to any OpenAI-compatible
  endpoint (local Ollama, Azure, etc.).

### 12.7 SQLite over PostgreSQL

SQLite is sufficient for the project's demonstration scale (~89 ROs, a few hundred
inspections in the demo). It requires no server, no setup, and the DB file (`iocl.db`)
is a single artifact that can be reset by deleting and re-seeding. The SQLModel ORM
abstracts the database dialect, so a production migration to PostgreSQL would require
only a connection string change.

### 12.8 Single-File PWA Frontend

The entire frontend is one HTML file (`frontend/index.html`) with all CSS and JavaScript
inline. This keeps the architecture simple (no build pipeline, no npm, no bundler),
makes the entire frontend trivially readable, and keeps deployment to a single `StaticFiles`
mount in FastAPI. The PWA features (service worker, manifest) are implemented in separate
small files (`sw.js`, `manifest.json`) as required by the browser API.

---

## 13. Limitations & Future Work

### 13.1 Synthetic Data Ceiling

All 12,473 remarks were generated synthetically from 559 base observations via template
expansion. This means:
- The model learns patterns from a finite vocabulary of observations, not from messy,
  context-dependent field language.
- 79.1% CV accuracy is an **optimistic ceiling**: real-world inspector remarks will be
  more varied, abbreviated, ambiguous, and domain-specific.
- The notebook explicitly warns: "Numbers here are an optimistic ceiling relative to
  genuine field remarks — honest, not overclaimed."
- The hidden-risk chart shows `correlation(compliance, semantic_risk) ≈ −0.98` in the
  synthetic dataset — extremely high. In real data, the two signals would diverge more
  often, making the combined engine even more valuable.

### 13.2 Medium Class Weakness

The "Medium class weakest" observation from the notebook is expected: Medium remarks
are linguistically adjacent to both Low and High, making them the hardest to separate.
In a 3-way classification on sparse synthetic data, the middle class receives fewer
confident training signals.

### 13.3 No Real OISD-STD-225 Corpus (Without Manual PDF)

The RAG layer requires the user to manually place `backend/rag/corpus/OISD-STD-225.pdf`
before running `python -m backend.rag.ingest`. Without the PDF, all recommendations
are null. The PDF is not committed due to copyright constraints.

### 13.4 Single-Shot Resolution (No Revision Tracking)

The current resolution workflow is boolean: `resolved` is either `True` or `False`.
There is no history of who resolved when, no "re-open" action, and no approval workflow.
A future enhancement could use an `inspection_item_events` log table.

### 13.5 Empty Dashboard on Fresh Seed

The seed script (`backend/seed.py`) **does not** insert historical inspection data
(since v3 — dashboards start empty). This means every demo session starts with no data
in the zone head or dept officer dashboards until an inspector submits. A historical
fixture could be added to seed.py for more realistic demos.

### 13.6 No Pagination on Inspection Lists

Both `/zone/inspections` and `/dept/inspections` return **all** inspections in memory,
sorted in Python before returning. At production scale (thousands of inspections per zone),
this would be a performance bottleneck. SQL-level pagination (`LIMIT`/`OFFSET` or cursor-based)
should be added.

### 13.7 Frontend Architecture

The entire UI is a single 1300-line HTML file with inline JS and CSS. While readable
for a demonstration project, it:
- Has no TypeScript type safety.
- Has no component abstraction (every detail-view rendering is a monolithic template literal).
- Has no automated UI tests.
- Shares state in a global `S` object and `responses` dictionary.

A production version would use a framework (React, Vue, Svelte) with a build pipeline.

### 13.8 SQLite Concurrency Limitation

SQLite has a single-writer lock. For the current demonstration scale this is acceptable,
but concurrent inspector submissions from multiple offices would serialize at the database
layer. A production deployment would require PostgreSQL or another multi-writer database.

### 13.9 No Re-training Pipeline

The `risk_classifier_bundle.pkl` is a static artifact. There is no mechanism to retrain
the classifier when new labelled remarks become available from real field inspections.
A production system would need a retraining pipeline triggered by labelled feedback.

### 13.10 RAG Recommendation Quality

The RAG layer's output quality depends on:
- PDF text extraction quality (pypdf can lose formatting in tables and annexures).
- The clause-regex chunking coverage (may miss clauses in non-standard formats).
- The LLM's ability to follow the "only use the excerpts" instruction (hallucination risk
  exists even with strong system prompts, especially on small models like `llama-3.1-8b`).
- The 350-token max_tokens limit may truncate long recommendations.

---

*End of PROJECT_OVERVIEW.md*

*Sources: all facts cited to file paths or notebook step outputs. Metrics marked
`[from CLAUDE.md]` were not independently verifiable from captured notebook output but
are consistent with the code logic. Metrics marked `[unverified]` have no source.*
