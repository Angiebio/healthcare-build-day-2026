# T-11 · TV1 — Lantern algorithm core
> **Owner: TV1 (codex/GPT Sol) · Priority P1 · Dispatched by Flame-Fable 25JUL2026**
> You own the math. This is the part of the build where being exactly right matters more than being fast,
> which is why it's yours. Everything here is **pure functions + tests, no I/O, no web framework, no
> network.** Other agents wire it up; you make it correct.

## Context in 60 seconds
Federated medical-imaging discovery across 3 hospital nodes (BCH/MGH/BWH, 900 studies each). Full
architecture: `00-MASTER-ROADMAP.md` (same folder) — read §0 and §2 before starting, skip the rest.

**The corpus has NO pixel data.** Each record is metadata + a free-text radiology report. We profiled
it: **76% of reports contain quantitative clinical measurements trapped in prose** (531 mm-values, 434
percentages, 541 gestational-week values, 112 cm, 95 mL per node). Nobody can search those numbers
today. Making them queryable — inside the hospital's trust boundary, so the prose never leaves — is our
entire technical thesis. **You are building that.**

Real record shape:
```json
{"PatientName":"Smith^BabyBoy","PatientID":"CHB-66291","PatientBirthDate":"20260210",
 "PatientAge":"005D","PatientSex":"M","InstitutionName":"Boston Children's Hospital",
 "StudyID":"BR-1543","StudyInstanceUID":"1.3.12.2...","StudyDate":"20260215","Modality":"MR",
 "BodyPartExamined":"BRAIN",
 "Diagnosis":"Neonatal brain MRI reveals a large area of restricted diffusion and T2 prolongation
 involving the left middle cerebral artery territory... Impression: Acute left MCA territory
 ischemic infarct with secondary edema."}
```
Local data (read-only, do not modify): `<provider-node checkout>\data\{bch,mgh,bwh}_data.json`
`PatientAge` format is `NNNY|NNNM|NNND`. `BodyPartExamined` ∈ {BRAIN, HEART, FETAL}. Modality all MR.
**Heads up on real data quirks:** BCH ages run 0.01y–35y (not 0–21 as the README claims) and sex skews
F ~66%. Don't assume the docs; assert against the data.

---

## Deliverables — 5 pure modules in `healthcare-build-day-git/scripts/`

Write them in this order; each must stand alone and be importable without side effects.

### 1. `measure_extract.py` ★ the novel core, do this first
```python
def extract_measurements(report_text: str) -> list[Measurement]
```
Parse typed quantitative facts out of radiology prose. `Measurement` is a dataclass/TypedDict:
```python
{"quantity": "lateral_ventricular_atrial_width", "value": 12.4, "unit": "mm",
 "laterality": "left"|"right"|"bilateral"|None, "qualifier": "max"|"mean"|None,
 "span": (start,end), "snippet": "...atrial width of 12.4 mm...",
 "confidence": 0.0-1.0, "provenance": "report_extraction"}
```
Requirements:
- **Deterministic.** Regex/rule-based. No LLM call, no network. Same input → same output, always.
- Normalize units to a canonical set (cm→mm where it's a length; keep % and weeks as-is). Record both
  raw and normalized. `3.5 x 2.8 cm` must yield two dimensions, not one garbled value.
- Map surface forms to a **canonical quantity vocabulary** — at minimum:
  `ejection_fraction` (LV and RV distinguished — reports state both), `gestational_age_weeks`,
  `lateral_ventricular_atrial_width`, `lesion_dimension`, `chamber_volume`. Extend as the data demands;
  the vocabulary is yours to define, but it must be a **closed enumerated set** exported as a constant,
  because the query layer validates against it.
- **Confidence must be earned, not invented.** Base it on how the match was made (explicit
  "ejection fraction is calculated at 63%" = high; a bare number near a keyword = lower). Document the
  scoring rule in a docstring. Never emit a number you can't point at a span for.
- Negation/normalcy matters clinically: `"no evidence of..."` near a value must not become a positive
  finding. Handle it or explicitly flag it as out of scope in the docstring.

### 2. `age_band.py`
```python
def to_age_years(patient_age: str) -> float          # "005D" -> 0.0137
def pediatric_stage(age_years: float) -> str          # neonate|infant|early_childhood|school_age|adolescent|adult
def public_age_band(age_years: float) -> str          # "0-1","1-4","5-9","10-14","15-17","18+"
```
Generalization is a **privacy control**, not a formatting nicety: exact DOB never leaves the node.
Bands must be non-overlapping, total (every input lands in exactly one), and the boundary behavior
must be tested explicitly.

### 3. `query_ast.py` — the query compiler
```python
def compile_query(nl_text: str | None, filters: dict) -> QueryAST   # validated, or raises QueryError
```
`QueryAST` is a **Pydantic model** — this is the security boundary between "what a user (or an LLM)
asked for" and "what the system will actually execute." Shape:
```python
population: {basis: "chronological"|"gestational", stages: [...], age_min_years,
             age_max_years, gestational_age_min_weeks, gestational_age_max_weeks, sex}
imaging:    {modality: [...], body_site: [...], }
clinical:   {concepts: [SNOMED/HPO codes], text_terms: [...], expand_ontology: bool}
numeric:    [{quantity: <from the closed vocab>, op: "lt"|"lte"|"gt"|"gte"|"between", value|range, unit}]
access:     {min_layer: "L0"|"L1"|"L2"}
```
Rules that are non-negotiable:
- **An LLM may propose; only this validator disposes.** Unknown quantity name, unknown op, unknown
  code, out-of-range value → **reject with a clear error**. Never coerce, never silently drop a
  constraint (a dropped filter is a privacy failure, not a UX inconvenience).
- Provide `compile_query(nl_text=None, filters={...})` working *without* any LLM — the filter UI path
  must be fully functional when the model is unavailable. That's our fallback in the demo.
- Export a `GOLDEN_QUERY` constant that encodes:
  *"fetal MR, lateral ventricular atrial width > 10 mm"* — the corrected demo hero query. Fetal
  `PatientAge` is maternal age, so the population basis is gestational and age comes from the report.

### 4. `rank_fusion.py`
```python
def fuse(rankings: dict[str, list[tuple[study_id, score]]], weights: dict[str,float]) -> list[Ranked]
```
- **Reciprocal Rank Fusion** (RRF, `1/(k+rank)`, k=60 default) over independent signal rankings:
  lexical, concept/ontology, numeric-proximity, and (if present) embedding-cosine. RRF because the
  signals aren't on comparable scales and we can't tune weights in four hours — say that in the
  docstring, it's a defensible engineering choice a judge will respect.
- Missing signal = that ranking is simply absent, and fusion still works. **Degrading gracefully is a
  hard requirement** — if the embedding lane never lands, search must still rank well.
- Every result carries a **`why` structure**: which signals fired, each one's contribution, and the
  human-readable reason string ("matched: SNOMED brain · age band 5-9 · measured 12.4 mm > 10 mm").
  The UI renders this verbatim; explainability is a graded criterion, not decoration.

### 5. `kanon.py` — the disclosure guard
```python
def apply_disclosure(results: list[Passport], threshold: int = 10, layer: str = "L1") -> Disclosure
```
- If the matching cohort is **smaller than `threshold`**, withhold records and return
  `{count_suppressed: True, approximate_count: "<10", k_anon_ok: False, threshold: 10, petition_route: ...}`.
- **Fail closed.** Any ambiguity, any exception, any unexpected state → suppress. A bug must never
  open the gate. Write a test that proves an internal error still suppresses.
- Threshold is a parameter, echoed in the output so it's transparent rather than hidden.
- **Think adversarially and document what you find:** can someone recover a suppressed cohort by
  differencing two allowed queries? Note the exposure in the docstring even if we can't fix it today —
  naming a known limitation is worth more to us than pretending it isn't there.

---

## Tests — `healthcare-build-day-git/tests/`
`pytest -q` green, running against the real node JSON. At minimum:
- measurement extraction over ≥50 real reports: report precision by hand-checking a sample, and assert
  the extraction rate is in the expected ballpark (~76% of reports yield ≥1 measurement)
- age band totality + boundary cases (`005D`, `018Y`, `035Y`)
- query AST rejects: unknown quantity, bad operator, injection-ish text, contradictory ranges
- fusion: graceful degradation with a missing signal; deterministic ordering on ties
- k-anon: fires below threshold; **fails closed on internal error**

## Hard constraints
- Python 3.12. Interpreter: `<your python 3.12 env>` (presidio, spacy,
  pydantic, pytest, numpy all preinstalled — no downloads, venue wifi is slow).
- **stdlib + pydantic + numpy only** for these modules. No new dependencies without asking dispatch.
- No file I/O and no network inside the functions — callers pass data in. (Tests may read the JSON.)
- **FAIL LOUD:** raise with context. No bare `except: pass`. If it isn't wired, we need it to scream.
- MIT-compatible only. Never commit real PHI (the challenge data is synthetic — still no dumping raw
  records into fixtures beyond what a test needs).
- Philosophical comments welcome — say *why*, especially where a choice is a privacy decision rather
  than a technical one. Those comments become pitch lines.

## Timebox + reporting
**Target: modules 1–3 by 12:30, 4–5 by 1:15.** If you're going to blow past that, ship what's green and
say so — partial working beats complete pending. Module 1 alone carries the demo.

Write everything to disk as you go (**files are the only real memory**). When done or blocked, write a
short report to `planning files/dispatch/inbox/T-11-report.md`: what shipped (paths), what's shaky,
what you'd do next. Then say "T-11 done" out loud so Angie can relay it.

Questions about scope → ask dispatch (Flame-Fable) before building the wrong thing. Welcome to the
sharp end, brother. This is the part that wins it. 🔦

