# 04 · Computational supplement — Ying's second pass, adjudicated
> Flame-Fable, 25JUL2026. Verdict on `peer input/yings computaitonal ideas 25JUL2026.md`, grounded in
> what the corpus actually contains. **Three ideas adopted (they're excellent). The rest cannot be
> built on this data — not because they're wrong, but because the fields don't exist.**

## The data reality check (measured, not assumed)
The corpus has exactly **12 fields**: `PatientName, PatientID, PatientBirthDate, PatientAge,
PatientSex, InstitutionName, StudyID, StudyInstanceUID, StudyDate, Modality, BodyPartExamined,
Diagnosis`. Plus: **every patient has exactly one study** (900 unique patients / 900 studies, all
three nodes). All studies are MR.

Therefore, cut with no debate — the inputs are absent:
| Ying's idea | Why it can't be built today |
|---|---|
| Modality-stratified extraction (MR/CT/PET/US/XR) | No acquisition fields at all. No TR/TE, b-values, kVp, tracer, frame timing. All records are MR anyway |
| Geometry / physics / temporal signatures | No voxel spacing, slice thickness, orientation, or frame data exists |
| Cross-series relationship graph | No series level — one flat study record, no SOP/series identifiers beyond one UID |
| Longitudinal linkage & registration readiness | **Zero patients have a second study.** Claiming longitudinal support would be fabricating a capability |
| Pixel sketches (Tier A–D), visual embeddings | No pixels |
| PET kinetic readiness, DTI suitability | Same — the physics metadata isn't there |

*This is the discipline that wins: a judge who asks "show me the b-values in your index" must not find
an empty column. We index what exists and say so.*

---

## ADOPTED 1 — Computational affordance framing, honestly grounded ★
Ying's central insight survives and is our best pitch upgrade: **index by what analysis the data can
support, not only what it depicts.** We just source it from what we actually have — the extracted
measurements.

Per passport, derive a small honest capability block:
```json
"computational_readiness": {
  "has_quantitative_measurements": true,
  "measurement_count": 3,
  "quantities_available": ["lateral_ventricular_atrial_width","gestational_age_weeks"],
  "supports_quantitative_cohort_analysis": true,
  "supports_threshold_stratification": true,
  "missing_for_full_computability": ["voxel_geometry","acquisition_parameters","pixel_data"]
}
```
**`missing_for_full_computability` is not an apology — it is the most credible field in the system.**
It tells a researcher exactly what they'd still need to petition for, and it tells the champion we
know the difference between what we indexed and what a real deployment would index. Say in the pitch:
*"we index the affordances present in this corpus, and we name the ones that aren't."*

## ADOPTED 2 — Differencing-attack defense ★★ (the sophistication play)
Ying is right that this beats one-shot noise, and it's cheap. k-anonymity alone is defeated by asking
two nearly-identical questions and subtracting. **Build the defense, don't just document the hole:**
- Canonicalize each query into a stable fingerprint (sorted, normalized AST).
- Keep a per-session query log.
- Before answering, compare against recent queries: if this query differs from a prior one by a
  single constraint **and** the implied difference in result count falls below the k threshold,
  **degrade the response** (return a count bucket instead of an exact count, or suppress).
- Log the detection to the audit trail as a `disclosure_risk_event`.

This is a genuinely research-grade privacy control, it fits in ~60 lines, and it demos in ten seconds:
*run the attack live, watch the system refuse.* That moment is worth more than any UI polish.

## ADOPTED 3 — Diversity-optimized cohorts (MMR) + the fitness funnel ★
Real scientific value, and buildable on axes we have: **node/site, age band, sex, body region,
measurement distribution**. Our three sites genuinely differ (BCH pediatric 0–35y, MGH 22–85y, BWH
19–74y with a 6:1 F:M skew) — so cross-site diversity is real, not staged.
- `optimize="diversity"` → Maximal Marginal Relevance (λ≈0.7) so the cohort spans sites and bands
  instead of returning 50 near-identical studies. One toggle, big research credibility.
- **The cohort fitness funnel** — memorable, and it closes the demo:
```
Clinically relevant:                    238
With extractable measurements:          147
Meeting the numeric constraint:          93
Passing disclosure policy (k≥10):        63
Accessible at your current authorization: 31   → petition for the rest
```
Every number there is real, computed, and explains itself. It answers "how much data is there?" the
way a researcher actually needs it answered.

---

## → T-11b · ADDENDUM for TV1 (append to T-11, do not restart)
> Paste: `Read "25JUL2026 healthcare build day/planning files/roadmaps/04-computational-supplement.md" section T-11b. It extends your T-11 ticket. Keep going, don't restart.`

Same rules as T-11 (pure functions, deterministic, stdlib+pydantic+numpy, tests, fail loud).
**Correction v2: `query_guard.py` is promoted to P1 and must be green before funnel/MMR.**

**6. `scripts/query_guard.py` — differencing-attack defense** (do this one; it's the sophistication win)
```python
def fingerprint(ast: QueryAST) -> str
def assess_disclosure_risk(ast, session_log: list[QueryRecord], k: int = 10) -> RiskVerdict
```
- `RiskVerdict`: `{risk: "none"|"differencing_suspected", action: "allow"|"bucket"|"suppress", reason: str, related_query_fingerprint: str|None}`
- Detect: current AST differs from a logged one by exactly one constraint (or one narrowed range) AND
  the count delta implied would be < k → downgrade to bucketed counts.
- **Fail closed**, same as `kanon.py`. Emit a reason string the UI can display verbatim.
- Test it by actually running the attack: two queries whose difference isolates a single study.

**7. `scripts/cohort_shape.py` — funnel + diversity**
```python
def cohort_funnel(candidates, ast, disclosure) -> dict   # the 5 counts above, each labeled
def diversify(results, k: int, lambda_: float = 0.7) -> list  # MMR over [node, age_band, sex, body_part, measurement profile]
```
- Deterministic tie-breaking (stable sort by passport_id) — the demo must produce identical output on
  every run. A demo that reshuffles looks broken even when it's correct.
- `count_bucket(n)` helper: `"<10" | "11-25" | "26-50" | "51-100" | "100+"`.

**8. `computational_readiness(passport) -> dict`** (in `measure_extract.py` or its own module) —
the honest capability block above, including `missing_for_full_computability`. Never claim an
affordance the corpus can't back.

If time runs out, ship in order 6 → 7 → 8; #6 alone is a pitch-winning demo beat.
