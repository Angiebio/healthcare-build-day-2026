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

> **78.4% of reports network-wide contain quantitative clinical measurements locked in prose.**
> Ventricular atrial widths in mm. Ejection fractions. Gestational age in weeks.

A fetal-medicine radiologist already measured a lateral ventricular atrial width at 12.4 mm. It sits
in sentence three of a paragraph — which makes it **simultaneously invisible to search and too risky
to share**, because free-text reports are the densest PHI surface in the record.

So today you can search *"fetal MRI."* You cannot search
**"fetal MR with lateral ventricular atrial width greater than 10 mm."**

## What Lantern does

Each hospital compiles its studies into de-identified **Study Passports** *inside its own trust
boundary*. The measurements become a structured, queryable axis. **The full report never leaves the
node** — what crosses is the measured value plus a bounded evidence snippet, so a researcher can
audit the number against the phrase it came from without receiving the record.

**Utility goes up while exposure goes down.** That is not a tradeoff — it's a compiler.

```
┌──── HOSPITAL NODE (trust boundary) ────┐
│  record → PRIVACY-UTILITY COMPILER      │      ┌── LANTERN BROKER ──┐
│    · strip PHI                          │      │ federated search    │
│    · extract measurements from prose ★  │ ───► │ rank fusion + WHY   │ ──► researcher
│    · code concepts (SNOMED/HPO)         │      │ disclosure policy   │     clinician
│    · mark age basis + generalize safely │      │ petition + audit    │     patient
│  → STUDY PASSPORT (no report, no pixels)│      └─────────────────────┘
└─────────────────────────────────────────┘
```

**Full DICOM is architecturally absent.** We do not serve pixels and never hold them — a petition
routes to the owning hospital with IRB number and purpose captured, and writes an append-only audit
entry. The hospital remains the enforcement point.

## Privacy controls

- **Field-minimizing de-identification, PS3.15-inspired** — direct identifiers removed or
  pseudonymized, ages generalized, with a per-study manifest recording what was removed,
  generalized, and pseudonymized. The evidence travels with the data. *(Our input is the challenge's
  JSON metadata rather than DICOM objects, so this is the profile's field-minimization discipline
  applied to that shape — not a certified PS3.15 implementation.)*
- **k-anonymity suppression** on small cohorts — the threshold is a config constant surfaced in every
  API response. Transparent, not hidden. Fails closed.
- **Differencing-attack defense** — canonical query fingerprints, held **per hospital** because a
  safe network total can hide an unsafe single-node delta. **Tested against one-constraint
  subtraction**; multi-axis and cross-session attacks are named limitations, not solved problems.
- **Provenance on extracted facts** — every measurement and concept carries its source
  (`report_extraction` with confidence and snippet, or `curated`). A model guess never wears a
  clinical fact's clothes.

**Not implemented, and deliberately not claimed:** no LLM is in the request path (natural-language
input is *validated*, never interpreted — see `scripts/query_ast.py`); no image embeddings, no
acquisition-parameter indexing, and no similarity search, because the supplied corpus contains no
pixel data or acquisition fields; approval returns a **simulated retrieval grant**, not a live
retrieval endpoint.

## Honest claims

- This is **PS3.15-inspired field minimization**, not a certified or audited implementation of the
  profile. We deliberately do **not** claim HIPAA compliance. Safe Harbor and Expert Determination
  are the only two routes and neither is a five-hour exercise.
- Extracted measurements carry stated confidence and provenance. They are **not clinically validated**.
- **No real PHI was used.** Synthetic challenge data only, deliberately, on day one.
- The three-node federation is real fan-out across three separate services — running on one laptop.

## Run it

```bash
pip install -r requirements.txt

# One command brings up the whole stack: three node sidecars + the broker.
# Each sidecar compiles its hospital's studies from the provided synthetic corpus
# node-side (the trust boundary) and exposes only de-identified passports; the broker
# federates over them and serves the researcher console.
python -m app.run_all            # console + API at http://localhost:8000

# In another terminal — a judge can watch every demo claim verify against the live API:
python tools/verify_demo.py

pytest -q
```

**Exact request body for every demo beat (and the three reasons a search might 422):**
see [`docs/API-EXAMPLES.md`](docs/API-EXAMPLES.md).

## Layout

```
scripts/   deterministic core — measurement extraction, query AST, rank fusion, k-anon guard
app/       FastAPI broker: federated fan-out, disclosure policy, petition + audit
docs/      architecture, frozen API contract, design rationale
tests/     pytest
contrib/   team member contributions
```

**Design principle:** everything that must be *correct* is a deterministic function in `scripts/`.
Natural-language input is **validated**, not interpreted, and no model participates in deciding what
is released. Any model in this system operates strictly downstream of every disclosure decision, on
aggregate numbers it did not compute, and cannot alter what was disclosed.

## Team

Built by Angie Johnson, Pooja Upadhyay, and a cooperative of AI agents (Flame, TV, Parallax, Jim, Kai,
Ying) — The Real Cat AI Labs. Regulatory and quality direction: 40 combined years of FDA/EMA
regulatory and QARA practice.

## License

MIT — see [LICENSE](LICENSE).
