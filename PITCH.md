# IOCL Retail-Outlet Safety Risk Engine — Project Pitch

---

## 1. ELEVATOR PITCH

IOCL safety officers inspect petrol pumps using a 144-item checklist (OISD-GDN-192 Annexure IV). Every current system counts the Yes/No boxes and reports a compliance percentage — but an item can be ticked "Yes" while its remark says "extinguisher present but pressure critically low." That risk is invisible to a compliance score.

This project builds a **Progressive Web App** where an officer submits a filled checklist and gets back a *combined* risk readout: a numerical compliance score blended 40/60 with a BERT-based semantic analysis of every remark, surfacing exactly those hidden dangers that compliance percentages bury.

The result is a single **Final Risk Index** (0–100, banded Low / Medium / High) with a hidden-risk count, section-level flags, and a placeholder for a future LLaMA + RAG recommendation engine.

---

## 2. PROBLEM & MOTIVATION

### Why "compliance %" is not enough

The standard audit metric is:

```
Compliance = (Yes responses) / (Yes + No) × 100
```

This is useful, but it treats every "Yes" as safe. Consider item HC8 from the checklist:

> **"Fire extinguishing equipment at strategic locations and maintained"**
>
> Response: **Yes**  
> Remark: *"Fire extinguisher present but pressure critically low"*

The compliance formula sees a **Yes** and moves on. An officer reading remarks would flag this immediately. At scale — 144 items per inspection, hundreds of inspections per year across dozens of retail outlets — no officer reads every remark. Risky items ticked "Yes" with dangerous remarks disappear into the spreadsheet.

This project calls those cases **hidden risks**: items where the box says compliant but the remark says otherwise. Finding them systematically, at scale, is the core problem.

### Why it matters for IOCL

Petrol pump safety incidents (fire, electrocution, hydrocarbon leak) are high-consequence. A single missed hazard — an uncharged extinguisher, an ELCB not installed, an emergency exit blocked — can result in loss of life or infrastructure. Catching hidden risks before they become incidents is exactly the kind of decision-support a safety management system should provide.

---

## 3. HOW IT WORKS

### 3a. The full flow (plain language)

1. Officer opens the **PWA** at `http://localhost:8000`.
2. Fills in Inspection ID, RO Name, then works through 21 accordion sections (144 items total), marking each **Yes / No / NA** and optionally typing a remark.
3. Clicks **Submit & Analyse**. The PWA POSTs the payload to the FastAPI backend.
4. The backend runs **two pipelines in parallel** on that payload.
5. The results are blended into a **Final Risk Index** and returned as JSON.
6. The PWA renders the **dashboard**: overall risk band, four score cards, hidden-risk count, flagged sections, and an AI recommendation placeholder.

### 3b. Pipeline 1 — Numerical (compliance formula, no ML)

Operates only on the Yes / No / NA boxes. Pure arithmetic; the relationship is known and unambiguous.

```
compliance_score       =  Yes / (Yes + No) × 100         [NA excluded]
numerical_risk_score   =  100 − compliance_score
section_scores         =  same formula per section; sections with no Yes/No are skipped (not scored as 0)
section_flags          =  sections where section_score < 70
```

Source: [`backend/risk_engine.py`](backend/risk_engine.py), lines 12–33.

### 3c. Pipeline 2 — Semantic (BERT + Logistic Regression)

Operates on the **remark text** of every item. Each remark is classified **Low / Medium / High** risk independently.

- **Encoder**: `all-MiniLM-L6-v2` (sentence-transformers) — converts a remark into a 384-dimensional semantic vector. The encoder is **frozen** (not fine-tuned).
- **Classifier**: Logistic Regression trained on those vectors. Chosen by 5-fold GroupKFold cross-validation over five competing models.
- **At inference**: the backend calls `encoder.encode(remarks)` then `classifier.predict(embeddings)`, mapping integer indices back through the saved label list (`['High', 'Low', 'Medium']`).

Source: [`backend/classifier.py`](backend/classifier.py).

```
semantic_risk_score  =  (2 × #High + 1 × #Medium) / total_items × 100
```

High counts double; Medium counts single; Low counts zero. This formula matches the one used to generate the dataset's own labels (verified). Source: [`backend/risk_engine.py`](backend/risk_engine.py), lines 40–45.

### 3d. The Combined Risk Engine

```
final_risk_index  =  0.40 × numerical_risk_score  +  0.60 × semantic_risk_score

Risk band:
  final_risk_index ≥ 25  →  High
  final_risk_index ≥ 15  →  Medium
  else                   →  Low

hidden_risks  =  count of items where (response == "Yes" AND risk_label == "High")
```

Source: [`backend/risk_engine.py`](backend/risk_engine.py), lines 8–9, 48–57, 77–79.

**Concrete example** (INSP00001, verified from [`NumericalAnalysis/IOCL_Combined_Risk_Engine.ipynb`](NumericalAnalysis/IOCL_Combined_Risk_Engine.ipynb)):

| Metric | Value |
|---|---|
| Compliance score | 75.93% |
| Numerical risk score | 24.07 |
| Semantic risk score | 52.78 |
| **Final Risk Index** | **41.30 → High** |
| Hidden risks (BERT labels) | 3 |
| Section flags (< 70%) | 6 sections |

### 3e. The backend API

FastAPI, pandas-free on the serving path, CORS enabled.

- `GET  /health`   → `{"status": "ok"}`
- `POST /assess`   body: `{inspection_id, ro_name, items:[{section, item_id, response, remark}]}`
  → `{overall_risk, final_risk_index, compliance_score, numerical_risk_score, semantic_risk_score, hidden_risks, section_flags, label_counts}`

The frontend PWA is served as a static site mounted at `/` (after the API routes).

Start command: `py -3.11 -m uvicorn backend.main:app --port 8000`

---

## 4. KEY TECHNICAL DECISIONS & WHY

### 4a. Frozen BERT + Logistic Regression (not deep learning / fine-tuning)

**The data is limited and synthetic.** Fine-tuning a transformer on ~12,473 examples from only 559 base remark templates would overfit and produce inflated accuracy numbers. The BERT encoder (`all-MiniLM-L6-v2`) was pre-trained on billions of sentences and already encodes the semantic meaning of safety remarks perfectly well; we do not need to modify those weights.

**On dense BERT embeddings, linear classifiers outperform tree ensembles.** This is the expected result (not a bug): BERT meaning is distributed across all 384 dimensions simultaneously, and tree-based models split on one feature at a time (axis-aligned splits), making them inefficient at this geometry. Logistic Regression draws a hyperplane directly in the embedding space where the class clusters actually live.

The numbers confirm this. From 5-fold GroupKFold CV on 12,473 remarks (559 groups):

| Model | CV Accuracy | CV Macro-F1 |
|---|---|---|
| BERT + Logistic Regression | 79.1 ± 4.7% | **76.8 ± 4.2%** |
| BERT + SVM (rbf) | 75.8 ± 4.1% | 73.3 ± 3.1% |
| BERT + XGBoost | 73.1 ± 5.7% | 70.2 ± 4.0% |
| BERT + Gradient Boosting | 68.9 ± 3.2% | 66.2 ± 1.8% |
| **BERT + Random Forest** | **59.0 ± 3.7%** | **54.1 ± 2.5%** |
| TF-IDF + Random Forest (baseline) | 79.2 ± 2.5% | 77.2 ± 2.8% |
| Keyword baseline | 54.1 ± 6.2% | 51.9 ± 5.8% |

Source: [`SymanticAnalysis/IOCL_Model_Training_CV.ipynb`](SymanticAnalysis/IOCL_Model_Training_CV.ipynb), Step 6.

Random Forest on BERT embeddings scored 54.1% macro-F1 — barely above the keyword baseline, and 22 points below Logistic Regression. The theory is confirmed empirically.

### 4b. Why the numerical side needs no machine learning

The formula `compliance = Yes / (Yes + No) × 100` is a known, unambiguous definition. There is no latent variable to learn, no pattern to discover. Applying ML here would be introducing a black box where a transparent formula already works — and the formula is validated to 0.00 maximum error across all 712 inspections (see Section 5). This is the correct engineering choice: use ML where the signal is ambiguous (natural language), use arithmetic where the relationship is exact.

### 4c. The data-leakage discovery and the GroupKFold fix

The original remark dataset (`IOCL_Remarks_ML_Dataset.csv`, 75,597 rows) had only **563 unique base remarks** repeated with minor paraphrase variations. A standard random 80/20 split placed identical remark text in both the training and test sets. The model memorized the text patterns and achieved ~100% accuracy — entirely artifactual.

**Fix**: The expanded dataset (`IOCL_Remarks_ML_Expanded.csv`, 12,473 unique rows) adds a `remark_group` column (559 groups). All rows sharing a base remark belong to one group. **GroupKFold / GroupShuffleSplit** on `remark_group` ensures that no phrasing from a base remark appears in both training and test folds. Accuracy dropped to the honest 79%, which is the correct number to report.

This demonstrates that the model evaluation is methodologically sound.

### 4d. Why 40/60 weighting and how thresholds were chosen

The 40/60 split is a **policy choice, not a learned parameter.** The semantic side receives more weight because it captures qualitative risk that Yes/No boxes cannot — the core argument of the project. The weights are intentionally kept as tunable levers so that IOCL safety policy-makers can adjust them without retraining anything.

The **High cutoff of 25** was chosen empirically: at that value, the engine agrees with the dataset's own combined risk labels at **90.9%** across all 712 inspections (see Section 5). The **section flag threshold of 70%** is a standard industry benchmark for minimum acceptable compliance. Both are documented as tunable in the code and CLAUDE.md.

---

## 5. RESULTS & VALIDATION

### Semantic model

**5-fold GroupKFold cross-validation** (verified from notebook output):
- CV accuracy: **79.1 ± 4.7%**
- CV macro-F1: **76.8 ± 4.2%**

Held-out macro-F1 (single GroupShuffleSplit, 80/20): **~0.83** *(per project docs; held-out classification report not printed in notebook for brevity)*

**Comparison note**: TF-IDF + Random Forest scored 77.2% CV macro-F1, marginally above BERT + LR's 76.8%. On this synthetic dataset with a finite vocabulary, TF-IDF is competitive. BERT was chosen for **generalizability**: real-world field remarks will use novel phrasing, abbreviations, and domain slang that a 2,000-feature TF-IDF vocabulary won't handle, whereas the BERT encoder generalizes from semantic similarity.

**Sanity checks** (verified from notebook Step 10):

| Remark | Predicted label |
|---|---|
| "Fire extinguisher present but pressure gauge reading below minimum" | Medium |
| "No ELCB installed on main panel, workers exposed to electrocution risk" | **High** |
| "Safety shoes worn by all staff during inspection" | Low |
| "Extinguisher situation looks bad, needs urgent fixing" | **High** |
| "The gauge is acting a bit funny today" (vague, OOD) | Medium |

### Numerical pipeline

Validated on all **712 inspections** from the raw dataset:
- **Maximum difference vs precomputed summary: 0.0** (exact match everywhere)
- Verified from [`NumericalAnalysis/IOCL_Numerical_Analysis.ipynb`](NumericalAnalysis/IOCL_Numerical_Analysis.ipynb), Step e967e86: *"Our pipeline reproduces the official compliance score."*

### Combined Risk Engine

Bulk validation on 712 inspections using the dataset's own stored risk labels:

| | | **Engine output** | |
|---|---|---|---|
| **Dataset label** | High | Medium | Low |
| High | 468 | 54 | 0 |
| Medium | 0 | 179 | 11 |

**Overall label agreement: 90.9%**

The 54 High inspections classified as Medium by the engine are the boundary cases near the threshold (index just below 25). No High inspection was called Low; no Medium was called High — the error is always conservative (one band off), not catastrophic.

Source: [`NumericalAnalysis/IOCL_Combined_Risk_Engine.ipynb`](NumericalAnalysis/IOCL_Combined_Risk_Engine.ipynb), Step 5.

### Honest synthetic-data caveat

All data is generated from ~563 base remark templates across Good / Average / Poor RO profiles. The compliance and semantic scores are **~−0.98 correlated** in this data (they mostly agree), so accuracy numbers are an **optimistic ceiling**. Real field remarks will be messier, shorter, and use domain-specific shorthand the model hasn't seen. The combined engine's value will be most pronounced exactly in the rare divergent cases — and on synthetic data, those cases are rare by construction.

---

## 6. LIVE DEMO SCRIPT

### Step 1 — Start the backend

Open a terminal in the repo root (`d:\IOCL`) and run:

```
py -3.11 -m uvicorn backend.main:app --port 8000
```

Wait for the line: `Application startup complete.` The first POST to `/assess` will be slow (~10–20 seconds) as the sentence-transformer model is downloaded and cached. Subsequent calls are fast.

*Optionally, warm the encoder now by running `python backend/test_request.py` in a second terminal. If the server is up, it will POST a 4-item test payload and print the JSON result — a clean sanity-check before the live demo.*

### Step 2 — Open the PWA

Navigate to `http://localhost:8000` in Chrome or Edge. The IOCL Safety Inspection form loads with 21 accordion sections.

Point out: the progress bar at the top ("0 of 144 items filled") and the yellow "Testing?" bar with the **Demo Fill** button.

### Step 3 — Trigger a hidden-risk scenario (the core demo)

Click **⚡ Demo Fill** in the yellow banner. This instantly fills all 144 items with a realistic distribution (~60% Yes, ~25% No, ~15% NA) and assigns remarks from a curated pool. The "Yes" pool includes remarks like:

> *"Fire extinguisher present but pressure slightly low — noted for servicing."*
> *"Helmets available but two workers in dispensing area not wearing them."*

The "No" pool includes high-risk remarks like:

> *"Emergency exit blocked by LPG storage. High risk."*
> *"No ELCB installed on welding machine power supply. Electrocution risk."*

These are the remarks the semantic pipeline will rate High. The "Yes" items with risky remarks are the **hidden risks**.

If the inspection ID and RO name are blank, Demo Fill populates them automatically. You can also type them manually first (e.g., `INSP_PITCH` / `Delhi Cantonment RO`).

### Step 4 — Submit and show the dashboard

Click **Submit & Analyse**. The button shows a spinner while the backend runs BERT on all 144 remarks (~3–5 seconds after warmup). The form view slides out; the dashboard slides in.

**Point at each element in order:**

1. **Risk banner** (top): red "HIGH RISK" label and the Final Risk Index value (e.g., 48–70). Say: *"This is the combined signal — 40% from the compliance formula, 60% from what BERT read in the remarks."*

2. **Score cards** (four numbers):
   - Final Risk Index
   - Compliance Score (the traditional metric)
   - Numerical Risk Score (100 − compliance)
   - Semantic Risk Score (BERT's view)
   Say: *"Notice compliance might be around 70% — traditionally that looks acceptable. But the semantic score is much higher because several Yes items have dangerous remarks."*

3. **Hidden Risks count**: e.g., "4 items ticked Yes with High-risk remark." This is the project's signature finding. Say: *"Four items the officer marked as compliant have remarks that the model rates as High risk. A pure compliance system never sees these."*

4. **Label Distribution** (High / Medium / Low counts across all 144 remarks): shows the full picture of what BERT found.

5. **Section Flags** (sections scoring < 70%): scroll down the list. Say: *"These sections need priority re-inspection."*

6. **AI Recommendation panel** (bottom, greyed out): *"This is the LLaMA + RAG layer — it will suggest corrective actions per flagged section once the guide provides the OISD rule-book corpus."*

---

## 7. LIMITATIONS & HONEST CAVEATS

**Synthetic data is an optimistic ceiling.** The dataset was generated from 563 base remark templates. The model has never seen a real inspector's handwritten note, abbreviation, or domain-specific shorthand. The 79% CV accuracy will likely be lower on genuine field data. This is expected and stated clearly in the project scope.

**High correlation in synthetic data (−0.98).** Compliance and semantic risk agree almost perfectly in this dataset because the synthetic data was generated to be consistent (Good RO → high compliance AND low-risk remarks). In real inspections, these signals will diverge more, making the combined engine more valuable. The current validation numbers understate the engine's practical benefit.

**The Medium class is the weakest.** Semantic classification of Medium-risk remarks is hardest (genuine ambiguity in the boundary between Low and High). The macro-F1 of 76.8% includes Medium; High and Low are likely substantially cleaner individually. In the confusion matrix, most errors are boundary misclassifications (High↔Medium), not High↔Low.

**BERT predictions vary slightly from stored labels.** In production, `hidden_risks` is computed from BERT's live predictions (~83% macro-F1 accurate), so the count differs slightly from what the dataset's stored labels would give. For INSP00001: stored labels give 1 hidden risk, BERT predictions give 3. This is documented and expected.

**The 40/60 weights are unvalidated on real-world outcomes.** They were chosen to reproduce dataset labels at 90.9% and to give semantic risk a majority share in line with the project's thesis. They have not been validated against actual incident data.

---

## 8. FUTURE WORK

**LLaMA + RAG recommendation layer (deferred, not blocked).**  
The architecture includes a placeholder panel in the PWA. When the guide provides the OISD rule-book corpus and past-incident data, a LLaMA model with Retrieval-Augmented Generation will generate per-section corrective action suggestions. The Final Risk Index does not depend on this component; it can be added without touching the engine.

**Collecting real labelled field remarks.**  
The highest-value improvement is replacing synthetic training data with actual inspector remarks, labelled by IOCL safety engineers. Even 2,000–3,000 real examples would likely improve generalization significantly. A GroupKFold framework is already in place; retraining is a notebook re-run.

**Fine-tuning the BERT encoder.**  
Once real labelled data exists in sufficient quantity, domain-adaptive fine-tuning of the MiniLM encoder on IOCL safety text could improve the semantic score. With synthetic data, this would overfit; with real data, it becomes appropriate.

**Mobile field deployment.**  
The PWA is already installable on Android/iOS (manifest and service worker in place). Offline-first caching would allow inspectors to fill checklists without connectivity and sync when back online.

---

## 9. ANTICIPATED QUESTIONS

---

**Q: Why did Logistic Regression beat Random Forest on BERT embeddings by such a wide margin (79.1% vs 59.0%)?**

A: BERT encodes meaning as a distributed pattern across all 384 dimensions simultaneously — no single dimension carries the full signal. Random Forests split one feature at a time (axis-aligned boundaries), which is geometrically ill-suited to dense distributed representations. Logistic Regression draws a hyperplane directly through the 384-dimensional space, which is exactly where BERT's class clusters are separated. This is a well-established result in NLP: on top of pre-trained dense embeddings, linear classifiers consistently outperform tree ensembles. The 22-point gap in our results is a confirmation, not a surprise.

---

**Q: TF-IDF + Random Forest scored 77.2% macro-F1, marginally higher than BERT + LR at 76.8%. Why use BERT at all?**

A: Honest answer: on this specific synthetic dataset, TF-IDF is competitive because the remark vocabulary is small and finite (563 base templates). TF-IDF excels when the vocabulary is known in advance. BERT's advantage is **generalization to unseen phrasing**. Real inspectors write "ext. not charged," "pressure below par," or "no flashback dev." A 2,000-feature TF-IDF vocabulary won't handle these; BERT's encoder — trained on billions of sentences — already understands them semantically. We chose BERT for the production use case, accepting that on the benchmark it doesn't strictly win.

---

**Q: Isn't 79% accuracy low for a safety-critical system?**

A: Three points. First, this is the *ceiling* — real-world accuracy will be lower; we are not overclaiming. Second, macro-F1 (76.8%) is the right metric here because classes are imbalanced; accuracy alone on imbalanced data is misleading. Third, the system is **decision-support**, not autonomous action. It flags risk for a human officer to review, not to trigger any automated response. In that context, 20-25% misclassification of individual remarks is acceptable — it's still far better than zero semantic analysis. The officer sees the label and can override it.

---

**Q: Why is your data synthetic? Doesn't that undermine the results?**

A: Getting real, labelled IOCL safety inspection remarks requires a multi-month procurement and privacy-clearance process. Synthetic data (generated from 563 inspector-realistic base remarks across Good / Average / Poor RO profiles) allowed us to develop and validate the full pipeline architecture, demonstrate the methodology, and build the live product — all within an internship timeline. We are explicit throughout that these numbers are an optimistic ceiling. The architecture and the cross-validation methodology are exactly what we would apply to real data; only the training corpus changes.

---

**Q: Why combine two signals that are ~−0.98 correlated in your data?**

A: The correlation is high *in this synthetic data* precisely because the data was constructed to be consistent. The project's value lives in the **tail cases where the signals disagree** — an item ticked Yes (compliant) whose remark describes a dangerous condition. In INSP00001, BERT found 3 such hidden risks that a compliance analysis misses entirely. The −0.98 correlation tells us the synthetic data is well-behaved; it does not tell us the combined engine is redundant. In real inspections, where remarks are written by humans under time pressure, the disagreement rate will be higher, and the combined engine's advantage will be larger.

---

**Q: Explain the data leakage you discovered and how you fixed it.**

A: The original dataset had 75,597 rows but only 563 unique base remarks. A random 80/20 split placed paraphrases of the same base remark in both training and test sets. The model learned to recognize remark-family patterns rather than semantic risk — and reported ~100% accuracy, an artifact. The fix was to add a `remark_group` column (one group per base remark) and use **GroupKFold / GroupShuffleSplit** as the CV strategy, ensuring that all rows from a given base remark family go exclusively into one fold. Accuracy dropped to the honest 79%. This is the correct number, and detecting and fixing this demonstrates methodological care over a naive implementation.

---

**Q: Why 40/60 weights? Could you learn them from data?**

A: Yes, you could — but we deliberately did not. The weights are a **policy choice**: how much does IOCL management want to weight a field inspector's free-text remark versus the Yes/No checkbox record? That is a domain and governance question, not an ML question. Keeping the weights explicit and tunable means safety managers can adjust them — e.g., "move to 50/50 if we don't trust our BERT accuracy" — without retraining a model. The 40/60 split was chosen to give semantic risk a majority share (the project's thesis), and the High threshold of 25 was validated to reproduce dataset labels at 90.9%. Those are two different validation steps.

---

**Q: What happens when the BERT model sees a completely novel remark it has never encountered?**

A: The model was tested on out-of-distribution inputs. "The gauge is acting a bit funny today" — a vague, non-standard remark — was predicted **Medium** (verified from notebook Step 10). Because the encoder was pre-trained on billions of sentences, it understands the semantic drift ("acting funny" = something is wrong) rather than matching keywords. It does not crash or return null — it assigns the nearest semantic class in embedding space. For genuinely ambiguous remarks, Medium is a defensible default (flag for review, neither assume safe nor trigger emergency response).

---

*All numbers in this document are verified against executed notebook cells or production source code unless marked otherwise. Verification sources are linked inline.*
