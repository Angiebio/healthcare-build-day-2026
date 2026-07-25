# Lane tickets T-12 … T-16 — Lantern build
> Dispatched by Flame-Fable 25JUL2026. Read `00-MASTER-ROADMAP.md` §0+§2 and `02-API-CONTRACT.md` first.
> All code lands in `healthcare-build-day-git/`. Fresh code only. Report to `dispatch/inbox/T-NN-report.md`.
> Python: `<your python 3.12 env>` (everything preinstalled, no downloads).

---

### T-12 · Privacy–Utility Compiler + Passport   [P1] [owner: Flame-Fable] [status: working]
**WHY:** criteria 1+3. This is the trust boundary made real, and the thing the champion cares about.
**BRIEF:** `scripts/compiler.py` + `scripts/passport.py`. Takes a raw node record → emits a Study
Passport per the contract. Steps: PHI strip (name/ID/DOB/institution → removed or salted hash) →
call TV's `extract_measurements` → concept coding via `scripts/terminology.py` (curated ~8-concept
SNOMED/HPO map behind a `TerminologyService` interface, mock↔real swap is one class) → age band +
pediatric stage → date shift (consistent per pseudonym, preserves intervals) → `deid_manifest`
listing exactly what was removed/generalized/hashed → provenance stamp.
**Acceptance:** compiles all 2,700 records in <10s; **zero raw prose in any output** (assert it);
manifest counts are accurate; running twice gives byte-identical output for the same input.
**Interfaces TV depends on:** import his functions, don't reimplement. If his module isn't landed yet,
code against the signatures in T-11 and stub locally — never block on another lane.

### T-13 · Broker API + policy engine + petition/audit   [P1] [owner: Flame1] [status: open]
**WHY:** criterion 2. The federation and the governance are the product.
**BRIEF:** `app/` FastAPI on :8000 implementing `02-API-CONTRACT.md` exactly. Async fan-out to the 3
nodes (`httpx.AsyncClient`, per-node timeout ~2s, one dead node degrades to a partial result with an
honest banner — never a 500). In-process cache of compiled Passports at startup (compile once, serve
many). Policy engine: role→tier field redaction server-side + TV's `apply_disclosure` k-anon guard.
Petition writes an **append-only** JSONL audit (`data/audit.jsonl`); no update or delete code path may
exist. `PATCH /petition/{id}` appends a decision event, it does not mutate the original.
**Acceptance:** all contract endpoints respond; kill a node mid-demo → search still returns with a
partial-results notice; audit file is append-only and visible in `GET /audit`; **an exception inside
policy code results in suppression, not disclosure** (prove it with a test).

### T-14 · Researcher frontend   [P1] [owner: Flame2, spawn ~11:45] [status: open]
**WHY:** criteria 2+4. The judges see this. It must look like a research instrument, not a startup.
**BRIEF:** Single-page app in `app/static/` (vanilla JS or React via CDN-free build — **no npm install
during the event**, wifi is slow; plain HTML/CSS/JS is a legitimate and fast choice here). Build
against the frozen contract immediately; do not wait for the backend.
Screens: (1) **search** — filter rail (modality · body site · pediatric stage · age range · **numeric
measurement constraint builder**) + NL box that degrades gracefully; (2) **results table** — dense,
tabular, one row per study, node badge, and the `why` reason string rendered verbatim; (3) **passport
detail** — measurements with provenance + confidence, and the **de-id manifest shown as evidence, not
hidden**; (4) **suppression state** — when k-anon fires, show the count band + petition CTA, styled as
a deliberate feature and not an error; (5) **petition form** → confirmation with audit ID; (6) role
switcher with a permanent "DEMO IDENTITY" banner.
**Aesthetic — this is graded:** read `.claude/skills/frontend-design` and the brand tokens. Dense,
legible, tabular, restrained. Think clinical research console: tight type, real data density, muted
palette, purposeful whitespace. **Explicitly avoid** the AI-default look — no purple→indigo gradient
hero, no uniform rounded cards with one colored edge, no centered emoji. Data density reads as serious
to this crowd.
**Acceptance:** every demo beat in MASTER §4 is clickable; works with the backend on localhost:8000;
no console errors; readable on a projector from the back of a room.

### T-15 · Red team   [P2] [owner: Parallax] [status: open]
**BRIEF:** Write to `planning files/dispatch/redteam/` ONLY — never the submission repo.
(a) **Attack the disclosure guard:** can you recover a suppressed rare cohort by differencing two
permitted queries, by paging, or by varying one filter at a time? Document every leak you find, with
the exact query sequence. (b) **Attack the compiler:** find records where measurement extraction
produces a wrong or dangerous value (negated findings read as positive, ranges mangled, units
confused) — we would rather find these than have a judge find them. (c) **License + claims audit:**
every dependency MIT/Apache/BSD, and every claim in the README/pitch either defensible or cut.
Flag any "HIPAA compliant" phrasing instantly — that's the one sentence that can lose us the room.
**Report by 1:30** so fixes still fit.

### T-16 · Architecture verification   [P2] [owner: Jim] [status: open]
**BRIEF:** Two passes, findings as a numbered list with `file:line` + severity (P1 blocks demo).
**~12:45:** does the trust-boundary claim actually hold *in the code*? Specifically: can the serving
layer reach raw prose through any import path? Is the audit genuinely append-only, or is there a write
path that could rewrite history? Does role→tier redaction happen server-side only?
**~1:45:** trace one request end to end (UI → broker → node → compiler → policy → response); break it
on purpose and confirm it fails loud rather than silently returning something plausible.
Write to `dispatch/inbox/T-16-verification.md`.

### T-17 · "Bring your own DICOM" lane   [P3 — ONLY if core is green by 1:15] [owner: unassigned]
**WHY:** the challenge corpus has no pixels and no acquisition parameters. This lane proves the
compiler generalizes to *real* DICOM — and lets us honestly demo the acquisition axis we otherwise
had to cut. It's the bells-and-whistles beat, and it costs nothing to skip.
**Use the DICOM already on disk — do NOT download from OpenNeuro.** Venue wifi is slow, OpenNeuro is
mostly BIDS/NIfTI rather than DICOM, and licensing would need checking under time pressure. We have
real MIT-licensed brain/abdomen MR at
`planning files/dicom-imaging-lab/data/pydicom-brain/*.dcm` — verified 25JUL to contain:
`MR_small.dcm`: TR 4000, TE 240, slice thickness 0.8 mm, pixel spacing 0.3125, SE sequence, TOSHIBA
MRT50H1, **PatientName + PatientID + InstitutionName present** ·
`MR-SIEMENS-DICOM-WithOverlays.dcm`: 1.5T Siemens Avanto, TR 5.53/TE 2.81, **overlay planes present**
(burned-in annotation risk) · `emri_small.dcm`: 3T, BodyPartExamined HEAD.
**BRIEF:** `POST /ingest/dicom` (multipart upload) → `pydicom.dcmread` → run the SAME compiler →
return a Passport with an `acquisition` block populated (field strength, TR/TE, slice thickness,
pixel spacing, sequence, manufacturer) + a de-id manifest showing the **real** PatientName/PatientID/
InstitutionName that were stripped. If overlay groups (60xx) or `BurnedInAnnotation != NO` are
present, set release status `HUMAN_REVIEW_REQUIRED` and **refuse to derive a preview** — that refusal
is the demo moment, not a failure.
**Acceptance:** upload → Passport in <3s; zero PHI in the response; the same passport schema as the
federated corpus (proving one pipeline, two sources); pixels never leave the server.
**Pitch line it unlocks:** *"the federated corpus gave us reports; here's the same compiler on a real
DICOM, pulling the acquisition physics — and refusing to preview the one with burned-in overlays."*
**Cut without hesitation if the core demo isn't green.** This is garnish on a finished plate.

---

## Integration order (dependencies, so nobody blocks)
```
TV T-11 (pure functions) ─┬─► T-12 compiler ─► T-13 broker ─► T-14 frontend (already built on contract)
                          └─► T-13 policy (k-anon)                    ▲
              everyone stubs against signatures rather than waiting ──┘
```
**The rule that keeps 6 agents from deadlocking:** if the module you need isn't landed, write the stub
that matches its signature, keep moving, and swap it when it arrives. Never idle waiting on a lane.

