# 🔦 LANTERN — Master Roadmap
> **Track 1 · Boston Children's · federated DICOM discovery**
> Flame-Fable (dispatch) · v1.0 · 25JUL2026, written post-challenge-drop.
> Peer input synthesized: Kai (tiering + de-id rigor), Ying (passport + policy states + Lantern name).
> **This doc governs. Where it disagrees with peer input, it wins — because it's grounded in the actual data.**

---

## 0. The reframe that changes everything (read this first)

**The provided corpus has no pixels.** `snellutla-rh/provider-node` ships 3 nodes × 900 records of *JSON
metadata + a free-text radiology report*. No `.dcm`, no images. Both peer specs assume pixel data and
build radiomics/visual-embedding stories on top of it. **Those lanes are unbuildable on the real corpus
today.** Do not spend a minute on radiomics, defacing, or burned-in-OCR against this dataset.

What we found instead is better, and it's ours because we actually profiled the data:

> **76% of the reports contain quantitative clinical measurements locked in prose.**
> 531 mm-values, 434 percentages, 541 gestational weeks, 112 cm, 95 mL — across 900 BCH studies.
> Ventricular atrial widths. Ejection fractions. Lesion dimensions. Gestational age.

Today a researcher can search *"brain MRI, pediatric."* They **cannot** search
*"lateral ventricular atrial width > 10 mm in children under 8 with thin-slice MR."*
The number exists. A radiologist measured it. It's sitting in sentence three of a paragraph — which
means it is simultaneously **invisible to search** and **radioactive to share** (free text is the PHI
landmine). Every hospital is in this bind.

**Lantern's thesis:** compile the prose into structured, computable facts *inside the hospital
boundary*, index the facts, and never release the prose. The researcher gets a **new quantitative
search axis that does not exist today**, and the data owner ships **strictly less** free text than
they do now. Utility goes up as exposure goes down. That's not a tradeoff — it's a compiler.

> ### The line the whole pitch hangs on
> **Existing systems ask "may I have the scan?" Lantern asks "what does the scan already know — and
> how much of that can you have right now, without the scan moving at all?"**

Name: **Lantern** (Ying's, adopted). Tagline: **Open discovery. Governed pixels.**

---

## 1. What we are building (5 nouns, memorize them)

1. **Study Passport** — the compiled, de-identified, computable representation of one study. Ying's
   schema, trimmed to what our data can actually fill. This is the artifact.
2. **Privacy–Utility Compiler** — the ingest pipeline that turns a raw node record into a Passport:
   PHI strip → measurement extraction → concept coding → age banding → provenance stamp.
3. **Lantern Broker** — federated search across the 3 hospital nodes. Fans out, merges, applies
   disclosure policy, explains every match.
4. **Disclosure Policy Engine** — k-anonymity small-cell suppression + release-status states +
   role-aware field redaction. Fail-closed.
5. **Access Petition + Audit** — request full data → routes to the owning node → append-only audit
   entry. We broker; we never serve what we shouldn't hold.

**Everything deterministic lives in `scripts/`. The LLM narrates and parses natural language into a
*validated* query AST — it never decides what is released, never invents a number, never sees the
prose it isn't allowed to see.**

---

## 2. Architecture (one diagram, this is the slide)

```
   ┌────────── HOSPITAL NODE (trust boundary — BCH :8001 · MGH :8002 · BWH :8003) ──────────┐
   │  provider-node record  ── raw, PII-leaking, free-text report (as given, untouched)      │
   │           │                                                                             │
   │           ▼   PRIVACY–UTILITY COMPILER  (runs node-side, inside the boundary)           │
   │   ┌───────────────────────────────────────────────────────────────────────────┐        │
   │   │ 1 PHI strip: name/MRN/DOB/institution → removed or hashed pseudonym       │        │
   │   │ 2 MEASUREMENT EXTRACTION: prose → typed numeric facts  ★ the novel core    │        │
   │   │ 3 CONCEPT CODING: findings → SNOMED-CT / HPO / ORPHA (curated map)         │        │
   │   │ 4 GENERALIZE: DOB→age band + pediatric stage · date→shifted/interval       │        │
   │   │ 5 PROVENANCE: every field stamped native_tag | report_extraction | curated │        │
   │   └───────────────────────────────────────────────────────────────────────────┘        │
   │           │                                                                             │
   │       STUDY PASSPORT  ──── the ONLY thing that crosses ────►                            │
   │       (facts + codes + bands + embedding of the CLEANED summary. No prose. No pixels.)  │
   └─────────────────────────────────────────────────────────────────────────────────────────┘
                                              │
                        ┌─────────────────────▼──────────────────────┐
                        │            LANTERN BROKER                   │
                        │  NL → validated Query AST → federated fan-out│
                        │  hybrid retrieval + rank fusion + WHY-matched│
                        │  ▼ DISCLOSURE POLICY (k-anon, fail-closed)   │
                        └──────┬──────────────┬──────────────┬────────┘
                         Researcher      Clinician      Patient/family
                         (L1 facts)   (L2 + petition)   (L0 plain language)
                                              │
                                    PETITION → owning node → APPEND-ONLY AUDIT
```

**The claim that wins the champion:** computation goes to the data; only de-identified derivatives come
back; **the embedding is computed on the cleaned passport summary, never on the raw report** — so the
vector itself is structurally incapable of leaking PHI. (Ying flagged embeddings as governed data. We
go one better and make them safe by construction.)

---

## 3. Privacy tiers (four, over the same study)

| Tier | Audience | Contents | Prose? | Pixels? |
|---|---|---|---|---|
| **L0 Public/Patient** | patients, public | codes in plain language, modality, body region, age band, "a small cohort exists at 2 nodes" | no | no |
| **L1 Researcher** ★ | computational researchers | full Passport: typed measurements, acquisition facts, codes, age band, quality, embedding, **cohort export** | no | no |
| **L2 Clinician** | verified clinicians | L1 + narrower age band + owner contact route | no | no |
| **L3 Source** | data owner only | **NOT SERVED — petition only.** Routes to owner with IRB/purpose + audit | — | — |

**Release states** (Ying's, adopted — no fake "HIPAA score"):
`BLOCKED · HUMAN_REVIEW_REQUIRED · PUBLIC_CATALOG_ONLY · CONTROLLED_DERIVATIVE · APPROVED_DEIDENTIFIED · OWNER_AUTHORIZED_SOURCE_ACCESS`

**Language discipline (P1 — Pooja + Angie enforce):** say **"PS3.15-aligned de-identification with
policy-gated release evidence."** NEVER say "HIPAA compliant." Safe Harbor / Expert Determination are
the only two roads and we drove neither in five hours. Say the accurate thing; it's more impressive.

---

## 4. The four demo beats (build backward from these)

1. **The impossible query.** *"Pediatric brain MR, ventricular atrial width over 10 mm, under 8 years."*
   Returns real hits across BCH+MGH+BWH. **This query cannot be run on any system in that room today.**
2. **Explain the match.** Open a result: matched on SNOMED brain + age band 5-9 + **measured 12.4 mm
   (extracted from report, provenance: report_extraction, confidence shown)** + FLAIR synonym.
   Each fact says where it came from. A model guess never masquerades as a clinical fact.
3. **Privacy holds under pressure.** Narrow to a rare finding → cohort drops below k → results
   **suppress to counts + petition pathway**, and the Passport shows exactly what was stripped.
4. **Governed access.** Petition → routes to owning hospital → owner approves in their view → audit
   entry appears, append-only. *"We never held the pixels. We brokered the request."*

---

## 5. Scope cutline (memorize the order — this is how we don't die)

**Must genuinely work (never cut):**
- Compiler: PHI strip + **measurement extraction** + age banding + provenance
- Federated fan-out across the 3 real nodes with per-node policy
- Hybrid search with **numeric range queries** + explainability
- k-anon suppression demonstrably firing
- Petition → owner route → append-only audit
- Researcher view, end to end

**Cut in this order when time bites:**
patient view → clinician view → live embedding (fall back to deterministic lexical+numeric ranking)
→ LLM query parsing (fall back to the filter UI, which must always work) → SNOMED breadth (5 curated
concepts is enough) → cohort CSV export.

**Cut immediately, do not debate:** radiomics · defacing · burned-in OCR (no pixels exist) · real
SNOMED server · Orthanc/Docker (no Docker on this laptop) · viewer · diagnosis model · auth beyond a
demo role-switcher with a visible "DEMO IDENTITY" banner · blockchain · homomorphic anything.

**Never cut:** the compiler and the petition/audit flow. Those two *are* criteria 1 and 3.

---

## 6. Lanes and owners

| Lane | Owner | Deliverable | Ticket |
|---|---|---|---|
| **Algorithms** (measurement extraction, query AST, rank fusion, k-anon) | **TV1** | `scripts/` pure functions + tests | T-11 → `01-TV-ticket-algorithms.md` |
| **Compiler + Passport + node adapters** | **Flame-Fable** | `scripts/compiler.py`, `passport.py` | T-12 |
| **Broker API + policy engine + petition/audit** | **Flame1** | `app/` FastAPI, frozen contract | T-13 |
| **Researcher frontend** | **Flame2** (spawn ~11:45) | dense, PACS-adjacent, not-AI-default | T-14 |
| **Red team** | **Parallax** | adversarial queries, k-anon bypass attempts, license audit | T-15 |
| **Architecture verify** | **Jim** | trust-boundary claim holds in the code; break-on-purpose | T-16 |
| **Champion + domain truth** | **Angie + Pooja** | office hours, release language, objection prep | — |
| **About page** | **Pooja + her Claude** | `contrib/pooja/` | T-07 |

**Frozen API contract lands by 11:30 and does not move.** Frontend builds against it immediately.

---

## 7. Clock (submission 3:00, internal freeze 2:15)

| Time | Milestone |
|---|---|
| now–11:30 | roadmaps out · TV dispatched · repo bootstrap · **API contract frozen** · 3 nodes running |
| 11:30–12:30 | compiler v1 (strip + measurements + bands) · broker fan-out live · frontend shell on contract |
| 12:30–1:15 | hybrid search + explainability · k-anon guard · passport detail view |
| 1:15–1:45 | petition + audit · role lenses · **the four demo beats runnable end to end** |
| 1:45–2:15 | integration hardening (run demo 3× clean) · README run-from-clone · adversarial pass |
| **2:15** | **feature freeze** — demo path only |
| 2:15–2:40 | record 2-min video (Win+Alt+R) |
| 2:40–2:50 | submit repo + video · verify public clone works |
| 2:50–3:00 | buffer. Hands off the keyboard. |

*Office hours are 1–3: Angie and Pooja are AWAY from the build 1:00 onward. Everything they need to
carry into that room must be true by 1:00.*

---

## 8. Honest-claims register (Pooja is the enforcer)

Every one of these appears in the README and the pitch, and every one is defensible:
- "PS3.15-**aligned**" — not certified, not audited. Aligned.
- Measurements are **extracted with stated confidence and provenance**, not clinically validated.
- k-anonymity threshold is a **config constant surfaced in the API response** — transparent, not hidden.
- Synthetic challenge data only. **No real PHI touched, deliberately, on day one.** Say it out loud.
- The 3-node federation is real fan-out over real separate services — but they run on one laptop.
  Say that too. Judges respect the person who names their own scaffolding.

*The humor is decorative. The math is structural. Go.* 🔦🔥
