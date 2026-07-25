# 🔦 Lantern

**Federated, privacy-tiered discovery for medical imaging.**
*Open discovery. Governed pixels.*

> Existing systems ask *"may I have the scan?"*
> Lantern asks *"what does the scan already know — and how much of that can you have right now,
> without the scan moving at all?"*

Built 25 July 2026 at The Open Accelerator Real-World Healthcare Hackathon (Red Hat, Boston) for the
Boston Children's Hospital challenge: *how do independent hospitals make their imaging data
discoverable and securely accessible without centralizing patient data?*

---

## The problem we found in the data

Pediatric and rare-disease research needs cohorts no single hospital holds. Today a researcher
approaches hospitals one at a time and waits months to learn whether enough data even exists.

We profiled the challenge corpus (3 hospital nodes × 900 studies) before designing anything, and
found the thing that shaped the whole build:

> **76% of the radiology reports contain quantitative clinical measurements locked in prose.**
> Ventricular atrial widths in mm. Ejection fractions. Gestational age in weeks.

A radiologist already measured a child's lateral ventricular atrial width at 12.4 mm. It sits in
sentence three of a paragraph — which makes it **simultaneously invisible to search and too risky to
share**, because free-text reports are the densest PHI surface in the record.

So today you can search *"pediatric brain MRI."* You cannot search
**"lateral ventricular atrial width over 10 mm, in children under 8."**

## What Lantern does

Each hospital compiles its studies into de-identified **Study Passports** *inside its own trust
boundary*. The measurements become a structured, queryable axis. The prose never leaves.

**Utility goes up while exposure goes down.** That is not a tradeoff — it's a compiler.

```
┌──── HOSPITAL NODE (trust boundary) ────┐
│  record → PRIVACY-UTILITY COMPILER      │      ┌── LANTERN BROKER ──┐
│    · strip PHI                          │      │ federated search    │
│    · extract measurements from prose ★  │ ───► │ rank fusion + WHY   │ ──► researcher
│    · code concepts (SNOMED/HPO)         │      │ disclosure policy   │     clinician
│    · generalize age → band, shift dates │      │ petition + audit    │     patient
│  → STUDY PASSPORT (no prose, no pixels) │      └─────────────────────┘
└─────────────────────────────────────────┘
```

**Full DICOM is architecturally absent.** We do not serve pixels and never hold them — a petition
routes to the owning hospital with IRB number and purpose captured, and writes an append-only audit
entry. The hospital remains the enforcement point.

## Privacy controls

- **PS3.15-aligned de-identification** with a per-study manifest showing exactly what was removed,
  generalized, and hashed. The evidence travels with the data.
- **k-anonymity suppression** on small cohorts — the threshold is a config constant surfaced in every
  API response. Transparent, not hidden. Fails closed.
- **Differencing-attack defense** — canonical query fingerprints detect an attacker subtracting two
  near-identical queries to isolate a rare cohort, and degrade the response.
- **Provenance on every fact** — each field is stamped `native_tag`, `report_extraction` (with a
  confidence and the source snippet), or `curated`. A model guess never wears a clinical fact's
  clothes.

## Honest claims

- This is **PS3.15-aligned**, not certified or audited. We deliberately do **not** claim HIPAA
  compliance — Safe Harbor and Expert Determination are the only two roads and neither is a
  five-hour exercise.
- Extracted measurements carry stated confidence and provenance. They are **not clinically validated**.
- **No real PHI was used.** Synthetic challenge data only, deliberately, on day one.
- The three-node federation is real fan-out across three separate services — running on one laptop.

## Run it

```bash
# 1. hospital nodes (provided boilerplate: github.com/snellutla-rh/provider-node)
HOSPITAL_NODE=BCH uvicorn main:app --port 8001
HOSPITAL_NODE=MGH uvicorn main:app --port 8002
HOSPITAL_NODE=BWH uvicorn main:app --port 8003

# 2. Lantern
pip install -r requirements.txt
uvicorn app.main:app --port 8000     # UI + API at http://localhost:8000

# tests
pytest -q
```

## Layout

```
scripts/   deterministic core — measurement extraction, query AST, rank fusion, k-anon guard
app/       FastAPI broker: federated fan-out, disclosure policy, petition + audit
docs/      architecture, frozen API contract, design rationale
tests/     pytest
contrib/   team member contributions
```

**Design principle:** everything that must be *correct* is a deterministic function in `scripts/`.
The language model parses natural language into a **validated** query AST and narrates results — it
never decides what is released, and never invents a number.

## Team

Built by Angie Johnson, Pooja Upadhyay, and a cooperative of AI agents (Flame, TV, Parallax, Jim, Kai,
Ying) — The Real Cat AI Labs. Regulatory and quality direction: 40 combined years of FDA/EMA
regulatory and QARA practice.

## License

MIT — see [LICENSE](LICENSE).
