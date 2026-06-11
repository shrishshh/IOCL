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

Final deliverable: a **multi-role authenticated PWA** where inspectors submit checklists,
zone heads review overall risk across their zone, and department officers see per-department risk.

## Architecture (v2 — multi-role platform)
```
Inspector fills checklist (144 items: Yes/No/NA + Remark)
        │
   ┌────┴─────┐
   ▼          ▼
NUMERICAL   SEMANTIC
(formula)   (BERT + Logistic Regression on remarks → Low/Med/High per remark)
   │          │
   └────┬─────┘
        ▼
 COMBINED RISK ENGINE  →  Final Risk Index = 0.40*numerical + 0.60*semantic
 assess_by_department()    Same formulas restricted to each dept's section
        ▼
 Backend API (FastAPI)  →  JWT-authenticated, role-scoped endpoints
        ↓
 SQLite DB (iocl.db)   →  persists inspections, items, dept risks
        ↓
 PWA front end          →  login → role-based view (inspector / zone_head / dept_officer)
```
A **LLaMA + RAG recommendation layer** is planned but **deferred** until the project guide
provides the "suggestion rule book". Placeholder panel in the PWA.

## Repository structure
```
IOCL/
├── CLAUDE.md
├── iocl.db                              # SQLite database (created by seed.py)
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
    ├── models.py        # SQLModel ORM tables
    ├── database.py      # engine (iocl.db), get_session, create_db_and_tables
    ├── auth.py          # JWT (python-jose), bcrypt (passlib), require_role()
    ├── risk_engine.py   # assess(), assess_by_department(), section_scores(); no pandas
    ├── classifier.py    # loads bundle + SentenceTransformer once at import
    ├── schemas.py       # Pydantic models (ChecklistItem etc.)
    ├── main.py          # FastAPI app; mounts all routers + serves PWA at /
    ├── seed.py          # idempotent seed: zones/offices/ROs/users + 40 historical inspections
    ├── smoke_test.py    # end-to-end API smoke tests (run while server is up)
    ├── requirements.txt
    ├── test_request.py
    └── routes/
        ├── __init__.py
        ├── auth_routes.py    # POST /auth/login, GET /auth/me
        ├── inspector.py      # GET /my/ros, POST /inspections
        ├── zone_head.py      # GET /zone/inspections, GET /inspections/{id}
        └── dept_officer.py   # GET /dept/inspections, GET /dept/inspections/{id}
```

## Data model (SQLite via SQLModel)
| Table | Key columns |
|---|---|
| `zones` | id, name |
| `offices` | id, code (OFF01…), name, city, state, zone_id |
| `ros` | id, code (RO0001…), name, office_id, profile |
| `users` | id, username (unique), password_hash, role, full_name, office_id?, zone_id?, department? |
| `inspections` | id, ro_id, submitted_by, submitted_at, overall_risk, final_risk_index, compliance_score, numerical_risk_score, semantic_risk_score, hidden_risks, label_counts_json |
| `inspection_items` | id, inspection_id (indexed), section, item_id, response, remark, predicted_label |
| `department_risks` | id, inspection_id (indexed), department, compliance, numerical_risk, semantic_risk, final_index, risk_band, hidden_risks |

## Org hierarchy (seeded from IOCL_Inspection_Summary.csv)
- **5 zones**: Delhi NCR, UP Region, Rajasthan Region, Punjab Haryana Region, Uttarakhand Region
- **20 offices**: OFF01 (Delhi Central) … OFF20 (Haridwar)
- **89 ROs**

## Roles & access scoping
| Role | Tied to | Can do |
|---|---|---|
| `inspector` | ONE office | Submit checklists for ROs in their office only. No risk results shown. |
| `zone_head` | ONE zone | View all inspections + full risk for all ROs in their zone. |
| `dept_officer` | ONE office + ONE department | View inspections for their office's ROs; only their department's items and risk. |

403 is returned for any out-of-scope access attempt.

## Departments (9 fixed — maps dept name → section string in items)
| Department | Section in checklist |
|---|---|
| PPE | PPE |
| Housekeeping | Housekeeping |
| Permits | Permits |
| Electrical | Electrical_Safety |
| Hydrocarbon | Hydrocarbon_Safety |
| Emergency | Emergency_Procedures |
| Confined | Confined_Space |
| Welding | Cutting_Welding_Grinding |
| Documentation | Documentation |

Items in other sections count toward overall risk but belong to no department.

## Risk scoring logic — EXACT, do not change without reason
Per item: `response ∈ {Yes, No, NA}`, `risk_label ∈ {Low, Medium, High}` (predicted by BERT).

- **compliance** = `Yes / (Yes + No) * 100`  (NA excluded)
- **section score** = same formula restricted to that section; **skip sections with no Yes/No**
- **numerical_risk_score** = `100 - compliance`
- **semantic_risk_score** = `(2*#High + 1*#Medium) / total_items * 100`
- **final_risk_index** = `0.40 * numerical_risk_score + 0.60 * semantic_risk_score`
- **risk band**: `index >= 25 → High` ; `index >= 15 → Medium` ; else `Low`
- **hidden_risks** = items where `response == "Yes" AND risk_label == "High"`
- **section_flags** = sections with score `< 70`
- **assess_by_department()** applies the same formulas restricted to each dept's mapped section

Weights (40/60) and thresholds (15/25, 70) are **tunable policy choices, NOT learned**.

## Auth (JWT)
- `POST /auth/login` — OAuth2PasswordRequestForm → `{access_token, token_type, role}`
- Token: HS256 JWT, 8h expiry, SECRET_KEY from env var (default dev key)
- All non-login endpoints require `Authorization: Bearer <token>`
- passlib[bcrypt] for hashing, python-jose for JWT; **pin bcrypt==4.0.1** (passlib incompatible with bcrypt>=4.1)

## Backend endpoints
```
GET  /health
POST /auth/login    (form: username, password)
GET  /auth/me

# Inspector
GET  /my/ros                  → [{ro_id, ro_code, ro_name, profile}]
POST /inspections             → {status:"submitted", inspection_id}

# Zone Head
GET  /zone/inspections        → [{id, ro_name, submitted_at, overall_risk, final_risk_index, compliance_score}]
GET  /inspections/{id}        → full detail: items + overall risk + dept breakdown + section_flags

# Dept Officer
GET  /dept/inspections                              → [{id, ro_name, submitted_at, dept_risk_band, dept_final_index}]
GET  /dept/inspections/{id}                         → {dept, dept_risk, items (dept section only, includes resolution fields)}
POST /dept/inspections/{id}/items/{item_db_id}/resolve  → resolved item; idempotent; 403 if wrong office/dept; 400 if label=Low
```

Items returned by both detail endpoints now include resolution fields:
`id, item_id, section, response, remark, predicted_label, resolved, resolved_by_name, resolved_at`
`resolved_at` is a UTC ISO string (e.g. `2026-06-11T12:04:38+00:00`); formatted in UI as "11 Jun 2026, 12:04".
Only Medium/High items are resolvable. Re-resolving is a no-op (idempotent).

## Seeding & demo credentials
Run once (idempotent):
```
py -3.11 -m backend.seed
```
Dashboards start empty — no historical data is seeded. All inspection data comes from live submissions.
Live submissions always use the BERT classifier.

### Demo accounts (password: `demo1234` for all)
**Zone Heads (5)**
| Username | Zone |
|---|---|
| zh_delhi_ncr | Delhi NCR |
| zh_up | UP Region |
| zh_rajasthan | Rajasthan Region |
| zh_punjab_haryana | Punjab Haryana Region |
| zh_uttarakhand | Uttarakhand Region |

**Inspectors (20)**
`insp_off01` through `insp_off20` — one per office.

**Dept Officers (18)** — for OFF01 (Delhi Central) and OFF08 (Lucknow):
`dept_ppe_off01`, `dept_housekeeping_off01`, `dept_permits_off01`, `dept_electrical_off01`,
`dept_hydrocarbon_off01`, `dept_emergency_off01`, `dept_confined_off01`, `dept_welding_off01`,
`dept_documentation_off01` (and same pattern for `off08`).

## Semantic model (the BERT side)
- Encoder: **`all-MiniLM-L6-v2`** (sentence-transformers), frozen → 384-dim vectors.
- Classifier: **Logistic Regression** (chosen by 5-fold GroupKFold cross-validation).
- Performance: ~**79% CV accuracy** (±5), ~**0.83** held-out macro-F1. Medium class weakest.
- Bundle: `risk_classifier_bundle.pkl` — contains `classifier`, `encoder_name`, `labels`, `embedding_dim`, `cv_macro_f1`. Does NOT contain the encoder; load `SentenceTransformer(bundle["encoder_name"])` separately.

## Data notes & history
- **Use `IOCL_Remarks_ML_Expanded.csv`** for the semantic model (de-duplicated, GroupKFold safe).
- All data is **synthetic** — accuracy is an optimistic ceiling; real field remarks will be messier.
- `overall_risk_level` in the dataset is the *combined* label (High/Medium only — no Low present).

## Status & roadmap
- [x] Semantic pipeline (BERT + LogReg), cross-validated, bundle saved
- [x] Numerical pipeline (compliance formula), validated to 0.0 diff vs Summary
- [x] Combined Risk Engine (40/60), validated ~90.9% vs dataset labels
- [x] SQLite database with SQLModel (iocl.db at repo root)
- [x] JWT auth — OAuth2 password flow, 8h tokens, bcrypt passwords
- [x] Role-based API — inspector / zone_head / dept_officer with scope enforcement
- [x] Idempotent seed script — 5 zones, 20 offices, 89 ROs, 43 demo users; dashboards start empty (live data only)
- [x] Multi-role PWA — login page + role-based routing + inspector checklist + zone head dashboard + dept officer dashboard
- [x] Issue-resolution workflow — dept officers mark Medium/High items resolved (name + UTC timestamp); zone heads see read-only badge
- [x] Question text on detail screens — `CHECKLIST_MAP` built from JS `CHECKLIST` array at page load; zero backend changes
- [ ] (Deferred) LLaMA + RAG recommendation panel — when the guide provides the rule book

## How to run
```bash
# First time only
py -3.11 -m pip install -r backend/requirements.txt
py -3.11 -m backend.seed

# Every time
py -3.11 -m uvicorn backend.main:app --port 8000
# Open http://localhost:8000
```

## Gotchas / conventions
- Folder is literally named **`SymanticAnalysis`** (misspelled). Match it exactly in paths.
- Resolve `.pkl` path relative to repo root (pathlib), never hardcode absolute path.
- The serving path must stay **pandas-free**; pandas is only for the analysis notebooks.
- **Pin `bcrypt==4.0.1`** — passlib 1.7.x is incompatible with bcrypt >= 4.1 (wrap-bug detection hits 72-byte limit).
- Tech stack: Python 3.11, FastAPI, SQLModel, SQLite, sentence-transformers, scikit-learn, python-jose, passlib.
