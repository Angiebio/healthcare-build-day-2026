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

> **78.4% of reports network-wide contain quantitative clinical measurements locked in prose.**
> The earlier 76% figure was BCH-only; brain-only extraction is lower.
> Ventricular atrial widths. Ejection fractions. Lesion dimensions. Gestational age.

Today a researcher can search *"fetal MRI."* They **cannot** search
*"fetal MR with lateral ventricular atrial width > 10 mm."*
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

**Everything lives in `scripts/` and is deterministic. As shipped there is no LLM anywhere in the
request path** — natural-language input is expanded against a curated synonym map and compiled into a
*validated* query AST by ordinary code. LLM query parsing was on the plan and was cut; we did not need
it, and its absence is worth stating out loud: **nothing in this system can invent a number, and
nothing statistical decides what is released.** Same discipline either way — an LLM may only ever
propose, and the Pydantic validator disposes.

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
   │       (typed facts + codes + bands + provenance. No full report. No pixels.             │
   │        Each fact carries a bounded evidence snippet: the clause it was read from.)      │
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

**The claim that wins the champion:** computation goes to the data; only de-identified derivatives
come back. The compiler runs **node-side, in a sidecar that is the only process permitted to touch the
raw record** — the broker has no import and no route that reaches `/api/studies`, which makes the
trust-boundary claim a `grep`, not a promise.

**What actually crosses, stated precisely.** The full radiology report never leaves the node. What
does cross is a **bounded evidence snippet per extracted fact** — roughly the clause the number was
read from — because a measurement a researcher cannot trace is a measurement they cannot trust, and
"12.4 mm, source withheld" is not a scientific claim. That is a deliberate disclosure decision, not an
oversight: we release the sentence fragment that justifies a number and withhold the narrative around
it. **Say it that way.** Claiming "no prose crosses" is both false and unnecessary — the honest
version is stronger, because it shows we priced the tradeoff instead of hiding it.

> *Cut, and not shipped: image/text embeddings and any vector similarity.* Earlier drafts of this
> document described embedding the cleaned summary. The corpus has no pixels and we cut the lane; there
> is no encoder and no vector index in this build. It is named here so nobody pitches it.

---

## 3. Privacy tiers (four, over the same study)

| Tier | Audience | Contents | Full report? | Evidence snippet? | Pixels? |
|---|---|---|---|---|---|
| **L0 Public/Patient** | patients, public | modality, body region, population band, existence-of-cohort signal | no | no | no |
| **L1 Researcher** ★ | computational researchers | full Passport: typed measurements with provenance + confidence, curated concept codes, population band, computational-readiness block | no | **yes** — the clause each number came from | no |
| **L2 Clinician** | verified clinicians | L1 + owner contact route | no | yes | no |
| **L3 Source** | data owner only | **NOT SERVED — petition only.** Routes to owner with IRB/purpose + audit | — | — | — |

*Not in any tier, because we did not build them:* acquisition parameters (TR/TE, field strength,
slice geometry — absent from this corpus), image quality metrics, embeddings/similarity, and
cohort CSV export. The passport says so itself: every record carries
`computational_readiness.missing_for_full_computability`, which names exactly what a real deployment
would still need to index. **That field is the most credible thing in the system — it is the build
telling you where it stops.**

**Release states** (Ying's, adopted — no fake "HIPAA score"):
`BLOCKED · HUMAN_REVIEW_REQUIRED · PUBLIC_CATALOG_ONLY · CONTROLLED_DERIVATIVE · APPROVED_DEIDENTIFIED · OWNER_AUTHORIZED_SOURCE_ACCESS`

**Language discipline (P1 — Pooja + Angie enforce):** say **"PS3.15-aligned de-identification with
policy-gated release evidence."** NEVER say "HIPAA compliant." Safe Harbor / Expert Determination are
the only two roads and we drove neither in five hours. Say the accurate thing; it's more impressive.

---

## 4. The four demo beats (build backward from these)

1. **Answer the stated ask.** *"Pediatric brain tumor"* expands across local tumor/neoplasm/glioma
   language. Show the semantic mapping before the numeric differentiator.
2. **The impossible query.** *"Fetal MR with ventricular atrial width over 10 mm."* Open BCH FT-4105:
   **14.1 mm left / 13.8 mm right**, both extracted with provenance and confidence. Population basis
   is gestational; maternal `PatientAge` is never mislabeled as fetal age.
3. **Privacy holds under pressure.** Narrow to severe >15 mm → BCH 7, MGH 6, BWH 3 → every node
   **suppresses to a bucket + petition pathway**. A near-duplicate query isolating <k records is also
   caught by the per-session differencing guard.
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

**Cut in this order when time bites** — and this is the historical plan; the strikethroughs are what
we actually spent:
patient view → clinician view → ~~live embedding~~ **(cut — deterministic lexical + numeric ranking
shipped instead)** → ~~LLM query parsing~~ **(cut — the filter UI and a curated synonym map carry it,
with no model in the request path)** → SNOMED breadth (a curated demonstration map shipped, as
planned) → ~~cohort CSV export~~ **(cut)**.

*We got further down this list than expected, which is why §1 and §3 above name the absences
explicitly rather than leaving the plan to imply we built them.*

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
