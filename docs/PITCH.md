# The pitch — Lantern
> Three minutes, spoken. Angie leads. Every number here is asserted by a test and reproducible
> offline; nothing in this document is aspirational. Demo click path: `docs/demo-runsheet.md`.

---

## 0:00–0:25 · The problem, in their words

> A child is treated for a brain tumour. Every few months there's another MRI, and a family waits to
> hear whether it grew. Researchers want to build tools that measure those changes consistently — and
> to do that they need examples from many children, many scanners, many hospitals.
>
> Pediatric cases are rare. No single hospital has enough. The scans almost certainly already exist,
> scattered across children's hospitals. Today there's no reliable way to find out where.
>
> So researchers go hospital by hospital and spend months on approvals just to learn whether enough
> data exists. Nobody in that chain is doing anything wrong. The problem is that **discovery and
> access have been welded together** — you can't ask "does this data exist?" without effectively
> asking "may I have it?"

## 0:25–0:45 · What we found in the data

> Before designing anything, we measured the corpus. **78% of the radiology reports contain
> quantitative clinical measurements written into the prose** — ventricular widths, ejection
> fractions, gestational age.
>
> A radiologist already measured a fetal lateral ventricular atrial width at 12.4 millimetres. That
> number is sitting in the third sentence of a paragraph. Which makes it, at the same time,
> **invisible to search and unsafe to release** — because free-text reports are the densest
> concentration of identifying information in the record.
>
> So today you can search "fetal MRI." You cannot search **"atrial width over 10 millimetres."**
> And 10 millimetres is not a number we picked — it's the diagnostic threshold for fetal
> ventriculomegaly.

## 0:45–1:00 · The move

> Lantern separates the two questions. Each hospital compiles its own studies into a de-identified
> **Study Passport** — inside its own boundary. The measurements become computable. The prose never
> leaves. Only the passport travels.
>
> **Utility goes up while exposure goes down.** That's not a tradeoff — it's a compiler.

## 1:00–2:20 · Demo — four beats

**1. The semantic ask** *(their requirement #1)*
> "Different hospitals use different words." Search **pediatric brain tumour** — expansion reaches
> neoplasm, glioma, mass, across nodes with different vocabularies. Each result says **why** it
> matched.

**2. The impossible query**
> **Ejection fraction under 40%** → **30 · 53 · 73** across three hospitals. Then
> **fetal atrial width over 10 mm** → **87 · 78 · 60.** Open one: the measurement, its confidence,
> and *the exact sentence it came from* — 14.1 mm on the left, 13.8 on the right. The parser splits
> bilateral findings, because a radiologist does.
>
> *This query cannot be run on any system in this building today.*

**3. Privacy holding under pressure**
> Narrow to **severe, over 15 mm** — clinically standard stratification. Now: **7, 6, and 3 cases.**
> All three hospitals fall below the k-anonymity threshold and **suppress independently.** No exact
> count crosses the wire — the response has no count field at all. What comes back instead is a
> petition route.
>
> And the subtraction attack: ask two nearly identical questions, subtract, isolate the cohort.
> **Watch it refuse.** Each hospital keeps its own query ledger, because a safe network total can
> hide an unsafe hospital delta.

**4. Governed access**
> Petition with IRB and purpose → routes to the owning hospital → **they** approve → the node issues
> a time-limited retrieval, and an append-only audit entry appears. Boston Children's auto-approves
> for a credentialed researcher; Brigham requires petition. **Same researcher, same query, different
> answers — each hospital's own rule.**
>
> We never held the pixels. We brokered the request.

## 2:20–2:45 · What we measured, and what we didn't claim

> We built the naive baseline and ran it. Keyword search for "severe ventriculomegaly" returns 29
> hits at Boston Children's where **7** are real — 24% precision — and it **cannot execute the
> threshold at all.** We report that as *not expressible*, not as recall zero, because that
> distinction is the entire thesis.
>
> Our own eval also records a case where plain keyword search **beats** us on precision. We left it
> in.
>
> This is **PS3.15-aligned de-identification with policy-gated release evidence.** We do not claim
> HIPAA compliance — Safe Harbor and Expert Determination are the only two routes and neither is a
> five-hour exercise. **No real patient data was used, deliberately.** Three real services, real
> fan-out, running on one laptop.

## 2:45–3:00 · Close

> The corpus we were given has no pixel data, so we index no image features and say so — every
> passport carries a field listing **what's missing for full computability.** A researcher deciding
> whether to spend six months on a cohort is better served by an honest inventory than an impressive
> one.
>
> **Existing systems ask "may I have the scan?" Lantern asks "what does the scan already know — and
> how much of that can you have right now, without the scan moving at all?"**
>
> Open discovery. Governed pixels.

---

## Q&A — pre-loaded

| They ask | Answer |
|---|---|
| Extraction errors? | Every measurement ships a confidence and the source sentence, so a clinician can check it in one glance. Not clinically validated — we'd adjudicate against a radiologist-scored set before deployment. |
| Embeddings leak PHI. | Ours are computed on the cleaned passport, never the raw report. Structurally incapable of carrying text we already removed. |
| k-anonymity is defeated by differencing. | Correct, so we built the defense — per-node query ledgers and canonical fingerprints. It's tested live. |
| Just search over metadata? | It's search over facts that exist nowhere as data today. We manufactured a queryable axis out of prose — inside the boundary, so the prose stays home. |
| Why trust the pipeline? | Don't. Audit it. Every passport ships a de-identification manifest, and a test suite tries to break the boundary over all 2,700 records. |
| Where does the compiler run? | On the hospital node. The broker has no import and no route that can reach raw data — verified, not asserted. |
| What about full DICOM? | Architecturally absent. We can't serve what we don't hold. |
| Does it scale? | The passport is the unit of scale — one compile per study, then search is cheap. Adding a hospital is adding a sidecar. |

**Never say:** "HIPAA compliant" · "differential privacy" (we do k-anonymity and count buckets) ·
"purely pediatric" (this synthetic BCH corpus runs to 35y).
