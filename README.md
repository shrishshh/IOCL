# IOCL RO Safety Inspection System

An internship project that analyses **IOCL Retail Outlet (petrol pump) safety inspections** using the OISD-GDN-192 Annexure IV checklist.

Traditional audits only count Yes/No boxes (a compliance score) and miss **hidden risk buried in remarks** — e.g. an item ticked "Yes" whose remark says *"extinguisher present but pressure below minimum"*. This system catches that by fusing two pipelines into a single **Final Risk Index**.

---

## Architecture

```
Officer fills checklist (144 items: Yes / No / NA + Remark)
         │
   ┌─────┴──────┐
   ▼            ▼
NUMERICAL     SEMANTIC
(formula)     (BERT + Logistic Regression → Low / Medium / High per remark)
   │            │
   └─────┬──────┘
         ▼
  Final Risk Index = 0.40 × Numerical + 0.60 × Semantic
         ▼
  FastAPI backend  →  PWA front end
```

---

## Repository Structure

```
IOCL/
├── README.md
├── CLAUDE.md                          # Project context for Claude Code
├── IOCL_Combined_Risk_Engine.ipynb    # Engine logic & validation notebook
│
├── NumericalAnalysis/
│   ├── IOCL_Inspection_Dataset.csv    # 102,528 rows — one per checklist item
│   ├── IOCL_Inspection_Summary.csv    # 712 rows — one per inspection
│   └── IOCL_Numerical_Analysis.ipynb
│
├── SymanticAnalysis/                  # (folder name is intentionally kept as-is)
│   ├── IOCL_Model_Training_CV.ipynb
│   ├── IOCL_Remarks_ML_Expanded.csv   # 12,473 unique remarks used for training
│   └── risk_classifier_bundle.pkl     # Trained BERT + LogReg model bundle
│
├── backend/
│   ├── __init__.py
│   ├── main.py          # FastAPI app — /health, /assess, serves PWA
│   ├── risk_engine.py   # Pure-function scoring logic (no pandas)
│   ├── classifier.py    # Loads bundle + SentenceTransformer at startup
│   ├── schemas.py       # Pydantic request/response models
│   ├── requirements.txt
│   └── test_request.py  # Quick smoke-test script
│
└── frontend/
    ├── index.html       # PWA — checklist form + dashboard (single file)
    ├── manifest.json    # PWA install manifest
    └── sw.js            # Service worker (offline caching)
```

---

## Risk Scoring Formulas

| Metric | Formula |
|--------|---------|
| Compliance | `Yes / (Yes + No) × 100` — NA excluded |
| Numerical Risk Score | `100 − compliance` |
| Semantic Risk Score | `(2 × #High + 1 × #Medium) / total_items × 100` |
| **Final Risk Index** | `0.40 × Numerical + 0.60 × Semantic` |
| Risk Band | Index ≥ 25 → **High** · Index ≥ 15 → **Medium** · else **Low** |
| Hidden Risks | Items where `response == "Yes"` AND `risk_label == "High"` |
| Section Flags | Sections with compliance score < 70% |

The High cutoff of 25 reproduces the dataset's own labels at ~92% accuracy across 712 inspections.

---

## Semantic Model

- **Encoder:** `all-MiniLM-L6-v2` (sentence-transformers), frozen — produces 384-dim vectors
- **Classifier:** Logistic Regression, selected by 5-fold GroupKFold cross-validation
- **Performance:** ~79% CV accuracy, ~0.83 held-out macro-F1
- **Bundle** (`risk_classifier_bundle.pkl`): contains `classifier`, `encoder_name`, `labels`, `embedding_dim`, `cv_macro_f1`

---

## Setup & Running

### 1. Install dependencies

```bash
pip install -r backend/requirements.txt
```

> First run downloads the `all-MiniLM-L6-v2` encoder (~90 MB) if not cached.

### 2. Start the server

Run from the **repo root** (`d:\IOCL`):

```bash
py -3.11 -m uvicorn backend.main:app --port 8000 --reload
```

Wait for:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

> **Windows note:** Use `py -3.11` explicitly — the dependencies are installed on Python 3.11. The default `python` may point to a different version.

### 3. Open the PWA

Go to **`http://localhost:8000`** in your browser.

### 4. Run the smoke-test (optional)

In a second terminal, with the server running:

```bash
py -3.11 backend/test_request.py
```

Returns a full JSON risk assessment for a 4-item sample inspection.

---

## API Reference

### `GET /health`
```json
{ "status": "ok" }
```

### `POST /assess`

**Request body:**
```json
{
  "inspection_id": "INSP00001",
  "ro_name": "Delhi Cantonment RO",
  "items": [
    { "section": "PPE", "item_id": "A1", "response": "Yes", "remark": "Helmets available but not worn by all workers" },
    { "section": "PPE", "item_id": "A2", "response": "No",  "remark": "Safety shoes not provided to contract workers" }
  ]
}
```

**Response:**
```json
{
  "inspection_id": "INSP00001",
  "ro_name": "Delhi Cantonment RO",
  "overall_risk": "High",
  "final_risk_index": 41.41,
  "compliance_score": 72.5,
  "numerical_risk_score": 27.5,
  "semantic_risk_score": 50.69,
  "hidden_risks": 7,
  "section_flags": { "Housekeeping": 42.86, "Permits": 60.0 },
  "label_counts": { "Low": 97, "Medium": 21, "High": 26 }
}
```

---

## PWA Features

- **144-item checklist** organised into 21 collapsible sections (OISD-GDN-192 Annexure IV)
- **Yes / No / N/A** toggle buttons with optional remark field per item
- **Live progress bar** tracking filled items
- **Demo Fill** button — instantly fills all 144 items with realistic sample data for testing
- **Dashboard** showing: overall risk band, Final Risk Index, compliance %, numerical & semantic scores, hidden risk count, section flags, label distribution
- **Installable PWA** with offline support via service worker
- **AI Recommendation panel** — placeholder for the planned LLaMA + RAG layer

---

## Roadmap

- [x] Semantic pipeline — BERT + LogReg, cross-validated, bundle saved
- [x] Numerical pipeline — compliance formula, validated against dataset
- [x] Combined Risk Engine — 40/60 blend, ~90.9% match vs dataset labels
- [x] FastAPI backend — `/health` and `/assess` endpoints, static file serving
- [x] PWA front end — checklist form → submit → risk dashboard
- [ ] LLaMA + RAG recommendation engine *(deferred — awaiting rule book from guide)*
