# IOCL RO Safety Inspection System

An internship project that analyses **IOCL Retail Outlet (petrol pump) safety inspections** using the OISD-GDN-192 Annexure IV checklist (~144 items, each with a Yes/No/NA response and a free-text remark).

Traditional audits only count Yes/No boxes (a compliance score) and miss **hidden risk buried in remarks** — e.g. an item ticked "Yes" whose remark says *"extinguisher present but pressure below minimum"*. This system catches that by fusing two pipelines into a single **Final Risk Index**, then generating grounded corrective actions via a RAG layer backed by OISD-STD-225.

---

## Architecture

```
Inspector fills checklist (144 items: Yes / No / NA + Remark)
         │
   ┌─────┴──────┐
   ▼            ▼
NUMERICAL     SEMANTIC
(formula)     (BERT + Logistic Regression → Low / Medium / High per remark)
   │            │
   └─────┬──────┘
         ▼
  Combined Risk Engine  →  Final Risk Index = 0.40 × Numerical + 0.60 × Semantic
  assess_by_department()    Same formulas restricted to each dept's checklist section
         ▼
  RAG Recommendation  →  For each Medium/High item: MiniLM retrieval over
  (BackgroundTask)        OISD-STD-225 Chroma index → Groq LLaMA generates
                          grounded corrective-action text + cited sections.
                          Stored in DB; never shown to inspector.
         ▼
  FastAPI backend  →  JWT-authenticated, role-scoped endpoints
         ↓
  SQLite (iocl.db)  →  persists inspections, items (incl. recommendations), dept risks
         ↓
  PWA front end  →  login → role-based view (inspector / zone_head / dept_officer)
                    Zone head + dept officer see inline RAG recommendations
```

---

## Repository Structure

```
IOCL/
├── README.md
├── CLAUDE.md                            # Project context for Claude Code
├── iocl.db                              # SQLite database (created by seed.py)
│
├── NumericalAnalysis/
│   ├── IOCL_Inspection_Dataset.csv      # 102,528 rows — one per checklist item
│   ├── IOCL_Inspection_Summary.csv      # 712 rows — one per inspection
│   └── IOCL_Numerical_Analysis.ipynb
│
├── SymanticAnalysis/                    # (folder name kept as-is)
│   ├── IOCL_Model_Training_CV.ipynb
│   ├── IOCL_Remarks_ML_Expanded.csv     # 12,473 unique remarks used for training
│   └── risk_classifier_bundle.pkl       # Trained BERT + LogReg model bundle
│
├── backend/
│   ├── main.py          # FastAPI app; mounts all routers + serves PWA
│   ├── models.py        # SQLModel ORM tables
│   ├── database.py      # engine (iocl.db), get_session, create_db_and_tables
│   ├── auth.py          # JWT (python-jose), bcrypt, require_role()
│   ├── risk_engine.py   # assess(), assess_by_department(), section_scores()
│   ├── classifier.py    # Loads bundle + SentenceTransformer once at import
│   ├── schemas.py       # Pydantic request/response models
│   ├── seed.py          # Idempotent seed: zones / offices / ROs / users
│   ├── smoke_test.py    # End-to-end API smoke tests (run while server is up)
│   ├── requirements.txt
│   ├── rag/
│   │   ├── corpus/OISD-STD-225.pdf  # Place PDF here before running ingest
│   │   ├── vectorstore/             # Chroma DB — created by ingest.py
│   │   ├── ingest.py    # Run once: py -3.11 -m backend.rag.ingest
│   │   ├── retriever.py # retrieve(query, k) → list[dict]
│   │   ├── llm.py       # Groq adapter (OpenAI SDK)
│   │   └── recommend.py # recommend_for_item(...) → {text, cited_sections}
│   └── routes/
│       ├── auth_routes.py   # POST /auth/login, GET /auth/me
│       ├── inspector.py     # GET /my/ros, POST /inspections (+ BackgroundTask for RAG)
│       ├── zone_head.py     # GET /zone/inspections, GET /inspections/{id}
│       └── dept_officer.py  # GET /dept/inspections, GET /dept/inspections/{id}, POST …/resolve
│
└── frontend/
    ├── index.html       # Single-file PWA — all roles in one page
    ├── manifest.json
    └── sw.js
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

Department risk uses the same formulas restricted to each department's mapped checklist section.

---

## Semantic Model

- **Encoder:** `all-MiniLM-L6-v2` (sentence-transformers), frozen — 384-dim vectors
- **Classifier:** Logistic Regression, selected by 5-fold GroupKFold cross-validation
- **Performance:** ~79% CV accuracy, ~0.83 held-out macro-F1
- **Bundle** (`risk_classifier_bundle.pkl`): contains `classifier`, `encoder_name`, `labels`, `embedding_dim`, `cv_macro_f1` — encoder loaded separately at runtime

---

## RAG Recommendation Layer

- **Corpus:** OISD-STD-225 (PDF), clause-level chunked and ingested into a Chroma vector store
- **Embeddings:** same `all-MiniLM-L6-v2` encoder already loaded for classification — no second model
- **LLM:** Groq LLaMA (`llama-3.1-8b-instant` by default) via the OpenAI-compatible SDK
- **Flow:** on inspection submit, a FastAPI `BackgroundTask` calls `recommend_for_item` for every Medium/High item and stores the result in `inspection_items.recommendation` — submissions are never blocked
- **Persistence:** recommendations are written once to the DB; subsequent page loads read from SQLite, no LLM call

---

## Roles & Access

| Role | Scope | Can do |
|------|-------|--------|
| `inspector` | One office | Submit checklists for ROs in their office; never sees risk results or recommendations |
| `zone_head` | One zone | View all inspections + full risk breakdown + inline RAG recommendations for all ROs in their zone |
| `dept_officer` | One office + one department | View inspections for their office's ROs; only their department's items and risk; can mark Medium/High items resolved |

---

## Setup & Running

### 1. Install dependencies

```bash
py -3.11 -m pip install -r backend/requirements.txt
```

> First run downloads `all-MiniLM-L6-v2` (~90 MB) if not cached.

### 2. Configure secrets

```bash
copy .env.example .env   # then edit .env and set GROQ_API_KEY
```

`.env` fields:
```
GROQ_API_KEY=<your key>
GROQ_MODEL=llama-3.1-8b-instant   # optional
```

### 3. Seed the database

```bash
py -3.11 -m backend.seed
```

Creates `iocl.db` with 5 zones, 20 offices, 89 ROs, and 43 demo users. Run this again after any schema change (drop `iocl.db` first — SQLite won't add new columns automatically).

### 4. Ingest OISD-STD-225 (once)

Place the PDF at `backend/rag/corpus/OISD-STD-225.pdf`, then:

```bash
py -3.11 -m backend.rag.ingest
```

Only needed once; re-run only if you replace the PDF.

### 5. Start the server

```bash
py -3.11 -m uvicorn backend.main:app --port 8000
```

Open **`http://localhost:8000`**.

---

## API Reference

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/login` | OAuth2 password form → `{access_token, token_type, role}` |
| `GET` | `/auth/me` | Returns current user info |

All other endpoints require `Authorization: Bearer <token>`.

### Inspector

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/my/ros` | List ROs in the inspector's office |
| `POST` | `/inspections` | Submit checklist; triggers RAG background task |

### Zone Head

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/zone/inspections` | List all inspections in the zone |
| `GET` | `/inspections/{id}` | Full detail: items, risk scores, dept breakdown, section flags, RAG recommendations |

### Dept Officer

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/dept/inspections` | List inspections for the officer's office |
| `GET` | `/dept/inspections/{id}` | Dept-scoped detail: items + dept risk + RAG recommendations |
| `POST` | `/dept/inspections/{id}/items/{item_id}/resolve` | Mark a Medium/High item resolved (idempotent) |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | `{"status": "ok"}` |

---

## Demo Credentials

Password for all accounts: **`demo1234`**

**Zone Heads**

| Username | Zone |
|----------|------|
| `zh_delhi_ncr` | Delhi NCR |
| `zh_up` | UP Region |
| `zh_rajasthan` | Rajasthan Region |
| `zh_punjab_haryana` | Punjab Haryana Region |
| `zh_uttarakhand` | Uttarakhand Region |

**Inspectors** — `insp_off01` through `insp_off20` (one per office)

**Dept Officers** — available for OFF01 (Delhi Central) and OFF08 (Lucknow):
`dept_ppe_off01`, `dept_housekeeping_off01`, `dept_permits_off01`, `dept_electrical_off01`,
`dept_hydrocarbon_off01`, `dept_emergency_off01`, `dept_confined_off01`, `dept_welding_off01`,
`dept_documentation_off01` (and same pattern for `_off08`)

---

## Status

- [x] Semantic pipeline — BERT + LogReg, cross-validated, bundle saved
- [x] Numerical pipeline — compliance formula, validated against dataset
- [x] Combined Risk Engine — 40/60 blend, ~90.9% match vs dataset labels
- [x] SQLite database with SQLModel ORM
- [x] JWT auth — OAuth2 password flow, 8h tokens, bcrypt hashing
- [x] Role-based API — inspector / zone_head / dept_officer with scope enforcement
- [x] Idempotent seed — 5 zones, 20 offices, 89 ROs, 43 demo users
- [x] Multi-role PWA — login + role-based routing + inspector checklist + zone head dashboard + dept officer dashboard
- [x] Issue resolution workflow — dept officers mark Medium/High items resolved (name + UTC timestamp); zone heads see read-only badge
- [x] RAG recommendation layer — OISD-STD-225 Chroma index + Groq LLaMA; grounded corrective-actions per Medium/High item; stored in DB; shown inline for zone head + dept officer
