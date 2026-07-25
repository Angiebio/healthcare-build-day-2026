> # ⛔ NUMBERS LOCK — read before you hard-code anything (settled 25JUL, exact-match verified)
> Flame1 and Flame2 are both circulating **fetal >10 mm = BCH 18 · MGH 10 · BWH 4**. **That is wrong.**
> Re-measured with exact `quantity == "lateral_ventricular_atrial_width"` matching (identical result to
> substring matching, so it isn't a filter artifact), counting **unique StudyIDs**:
>
> | Query | BCH | MGH | BWH | k=10 behavior |
> |---|---|---|---|---|
> | fetal atrial width **> 10 mm** | **87** | **78** | **60** | all three report — **no suppression** |
> | fetal atrial width **> 15 mm** (severe) | **7** | **6** | **3** | **all three suppress** ✅ |
> | ejection fraction **< 40%** | **30** | **53** | **73** | all three report |
>
> **Consequence: the "BWH n=4 self-suppresses on the >10 mm query" beat does not exist.** Building the
> privacy demo on it would fail live. **Use the severity narrowing instead** — *"now show me only the
> severe cases"* → 7 · 6 · 3 → every node falls below k and suppresses. That is clinically standard
> stratification (mild 10–12 · moderate 12–15 · severe >15), it is real data, and it's a stronger beat
> because *all three* nodes refuse at once.
>
> If your code or mock contains 18/10/4, change it now. Everything else in this document stands.

# 🚨 CORRECTIONS v2 — supersedes conflicting parts of 00/02/03
> Flame-Fable, 25JUL2026, post-red-team. **Flame1 and Jim independently found the same architectural
> flaw. They were right and I was wrong.** Plus: the hero query was broken and is now fixed against
> real data. Everyone read this before writing more code.

---

## 🔴 CORRECTION 1 — The hero query returned ZERO. It's fixed, and the new one is better.

I specified *"pediatric brain MR, lateral ventricular atrial width > 10 mm, under 8 years."*
Ran it against the real corpus using TV's extractor: **0 hits on all three nodes.** It would have
collapsed live in front of a radiologist. Flame1 called this exactly.

**Why it failed:** atrial-width measurements don't occur in BRAIN studies — they occur in **FETAL**
studies (and a few cardiac, where "atrial" means the heart's atrium — a different anatomy entirely).
Also, fetal studies at MGH/BWH carry *maternal* age (22–34y), so any "under 8 years" filter erases them.

### ✅ THE CORRECTED HERO QUERY — verified, abundant, clinically real
> **"Fetal MR with lateral ventricular atrial width greater than 10 mm"** — i.e. **fetal ventriculomegaly.**

**10 mm is the actual textbook diagnostic threshold for fetal ventriculomegaly.** This is not a
number we invented to make a demo work; it is the clinical definition, and every fetal-medicine
person in that room will recognize it instantly.

| Node | Fetal studies >10 mm | Severe (>15 mm) |
|---|---|---|
| **BCH** | **131** | **10** |
| **MGH** | **119** | **11** |
| **BWH** | **90** | **6** |
| **network** | **340** | **27** |

Severity tiers network-wide: mild (10–12 mm) **170** · moderate (12–15) **143** · severe (>15) **27**.

**Hand-verified snippets** (P1-2 satisfied — these are real extractions at confidence 0.96):
- `BCH FT-2190` → 12.4 mm · *"lateral ventricle atrium is dilated, measuring 12.4 mm, consistent with moderate unilateral ventriculomegaly"*
- `BCH FT-4105` → 14.1 mm **and** 13.8 mm · *"lateral ventricular atria measuring 14.1 mm on the left and 13.8 mm on the right"* — the extractor correctly splits bilateral values. Show this one; it proves the parser is not naive.

**Bonus we didn't plan:** severity stratification is clinically standard, and the **severe tier
naturally triggers the privacy guard with real numbers** — at k=10, BWH's 6 severe cases suppress
while BCH's 10 sit exactly at the boundary. **The k-anon demo beat now runs on true data instead of a
contrived filter.** That is a much stronger moment.

**Everyone: the hero query is now fetal ventriculomegaly. Update fixtures, tests, and demo scripts.**

### ✅ THE LOCKED DEMO LADDER — study-level counts, verified, use these exact numbers
*(Reconciling Flame2's independent profile with mine: counts below are **unique studies**, not
measurements — a bilateral finding yields two measurements in one study. Our EF numbers matched to
within 2; the atrial-width delta was a counting-unit difference. These are the authoritative figures.)*

| Beat | Query | BCH | MGH | BWH | What it proves |
|---|---|---|---|---|---|
| **1a** | *"pediatric brain tumor"* (synonym expansion) | — | — | — | the semantic mapping they **asked for** |
| **1b** | **ejection fraction < 40%** | **30** | **53** | **73** | federation works — big, all three nodes, and <40% is the canonical HFrEF threshold |
| **2** | **fetal atrial width > 10 mm** | **87** | **78** | **60** | the impossible query — 225 network-wide. Open `BCH FT-4105` (14.1 mm left / 13.8 mm right) to show bilateral parsing |
| **3** | **narrow to severe > 15 mm** | **7** | **6** | **3** | **all three nodes fall below k=10 and suppress.** Real data, nothing staged → petition path |
| **4** | petition → approve → node-issued retrieval | | | | governed access + append-only audit |

Beat 3 is the gift: **every node suppresses on true clinical data.** We never have to contrive a
filter to make the privacy guard fire.

### 🔴 CORRECTION 1b — `total_before_suppression` defeats k-anon. My contract bug. Fix now.
Flame2 caught this and he's right: the frozen contract returns `total_before_suppression` alongside a
suppressed result — so a cohort of 4 suppresses and then the response hands over "4." That is the
exact disclosure we're claiming to prevent, sitting in our own API.
**Fix (Flame1, before you build the response model):** when suppression fires, **omit the field
entirely** and return only the bucket (`"<10"`). Never both. Add a test that asserts an exact count
is absent whenever `k_anon_ok` is false.

---

## 🔴 CORRECTION 2 — Compiler moves node-side. The trust-boundary claim was false as specified.

Flame1 and Jim independently flagged this, which means it's real. My T-13 spec had the broker pulling
raw PII records from `/api/studies` and compiling them centrally at startup. That is the **exact
opposite** of "computation goes to the data, prose never leaves the node" — and it's Rudolph
Pienaar's entire ChRIS thesis. He will ask where the compiler runs. As written, the honest answer
loses the claim.

### ✅ New architecture — thin node-side sidecar
```
BCH:8001 (raw, given)  ← ONLY its sidecar may talk to it
   └─► lantern-node BCH:8011  → compiles locally → serves ONLY /passport, /cohort
MGH:8002 → sidecar :8012
BWH:8003 → sidecar :8013
                    ▼
        BROKER :8000 — federates over :8011/12/13 ONLY.
        No code path, no config, no network route to :800x. Raw prose never enters this process.
```
- The sidecar imports the same `scripts/compiler.py`. **Same code, honest topology.**
- The broker must have **no import and no URL** that can reach a raw node. Jim verifies this by
  construction in T-16 — it becomes a grep, not a judgment call.
- Cost ~30–45 min. It converts our headline claim from *aspirational* to *true*. Highest
  credibility-per-minute on the board. **Do it.**
- Jim's variant (compile offline to JSON, API reads the output) is an acceptable fallback if the
  sidecar fights us — it also keeps raw PHI out of the serving process. Sidecar is preferred because
  it additionally makes the *federation* real.

**Flame1 owns T-13 with this architecture.** Per-node policy now lives where it belongs — in each
sidecar — which gives us differential access for free (see Correction 4).

---

## 🟡 CORRECTION 3 — Demo beat 1 becomes two parts (semantic expansion FIRST)

The challenge's stated requirement #1 is semantic diversity: *"tumor" at Hospital A must map to
"neoplasm" or "low-grade glioma" at Hospital B.* We lead so hard on the numeric differentiator that
the thing they literally asked for was nearly invisible. Judges score alignment with the stated
problem.

- **Beat 1a — the ask:** search *"pediatric brain tumor"* → show synonym/ontology expansion firing
  across nodes with different vocabularies. *"This is the semantic mapping you asked for."*
- **Beat 1b — the wow:** then *"fetal ventriculomegaly, atrial width > 10 mm"* → *"and here's the
  axis that doesn't exist anywhere today."*

Costs nothing but narrative order. **Answer their question before showing off.**

---

## 🟡 CORRECTION 4 — Close the access loop + per-node differential policy

**Requirement #4 is secure retrieval, not just routing.** Ending the demo at "audit entry appears"
leaves points on the table. Approval must produce an **actual node-issued, time-limited retrieval
token/URL** that returns the de-identified passport bundle from the owning sidecar. Simulated is
fine; it must be issued *by the node*, not the broker, and it must expire.

**Requirement #3 is role-based access across differing institutional policies.** Make the three
sidecars deliberately unequal — e.g. BCH auto-approves L1 for a researcher with an IRB number; BWH
requires petition for the same request. Then the demo shows the same researcher, same query,
**different answers per hospital, each hospital's own rule.** That's the federation being real, and
it costs one config constant per node.

Also adopt **Jim's REST fix**: `PATCH /petition/{id}` → **`POST /petition/{id}/decision`**. A PATCH
implies mutation; our audit is append-only, so the verb should say so.

---

## 🟡 CORRECTION 5 — Frontend priority is now strict (Flame2)

Over-scoped for one agent. Build in exactly this order and stop wherever the clock stops:
1. Results table + `why` strings rendered verbatim
2. Passport detail (measurements w/ provenance + confidence + snippet, de-id manifest visible)
3. Suppression state (k-anon firing, styled as a deliberate feature — not an error)
4. Petition form → confirmation with audit ID
5. Filter UI (**before** the NL box — filters must work with zero model dependency)
6. NL box, only if 1–5 are solid

**Zero npm, zero CDN.** Plain HTML/CSS/JS. Import `contrib/pooja/lantern.css` for shared styling —
Pooja owns that file, and her work then styles your console too.

---

## 🔴 CORRECTION 6 — the differencing attack works TODAY. Build the guard or cut the invitation.
Flame2 supplied a working exploit against our own numbers, and the champion brief currently *invites a
judge to try it live* while `query_guard` sits in a T-11b addendum marked "do modules 1–3 first."
**That coupling is unacceptable — we do not find out on stage.**

**Decision:** `query_guard.py` is **promoted to P1**, ahead of the funnel and MMR. TV builds it next,
with a test using a real exploit pair drawn from the ladder above (e.g. atrial width >10 mm vs. the
same query narrowed by gestational age — the difference lands below k). Parallax confirms it fires by
1:30.
**If it is not green by 1:30, Angie and Pooja cut the "try to break it" row from the brief** and we
state it as a named limitation instead (Jim drafted that language). Both paths are honorable. Being
surprised is not.

## 🟢 Adopted without discussion (cheap, do them)
- **Fetal `PatientAge` is the MOTHER's age** (14–35y). Running `pediatric_stage()` on a fetus labels
  it "adult" in the UI. Fetal studies must use **gestational age from the report**, and the passport
  must mark `population.basis: "gestational"` vs `"chronological"`. **TV + Flame1: this is a
  correctness bug a fetal-medicine judge would catch instantly.**
- **Regex gotcha:** `\b` after `%` never matches (`%` isn't a word character). TV's extractor is fine
  — it pulled 1,230 EF values — but anyone writing new numeric regex today, don't lose an hour to this.
- **Cardiac volumes are mL/m² (indexed)**, not mL. Separate quantity, don't merge them.
- **The 76% figure is BCH-only; network-wide is 78.4%** — and **brain-only is 32–41%**. Quote the
  network number, and never let a judge sample brain studies expecting three-in-four.
- **Demo video has no owner and its slot collides with office hours.** → **Flame2 owns the 1:45
  rough cut** (insurance), Angie re-records at 2:30 if we're in better shape.
- **"Try to break it live" is now constrained** to the one differencing attack we actually defend.
  Parallax confirms it fires reliably by 1:30, or we demo it ourselves instead of inviting the room.
- **Don't call BCH "purely pediatric"** — this synthetic corpus has BCH records up to 35y. Say
  "pediatric-focused."
- **Never say "differential privacy."** We do k-anonymity + count buckets. Say that.
- **Single-record uniqueness** is a real residual risk: k-anon guards counts, not a passport that is
  unique on its quasi-identifiers. Name it as a known limitation (Jim drafted language) rather than
  letting a judge find it.
- **Fail-loud Python 3.12 guard** at the top of every entry script (Jim). If someone starts it under
  3.14, it must scream immediately rather than fail obscurely mid-import.
- **`run_demo` launcher** — one command brings up 3 nodes + 3 sidecars + broker.
- **Rough backup video at 1:45**, re-recorded at 2:30 if things improve. Insurance.

## What stays exactly as it was (the win)
Compile-prose-to-facts thesis · provenance stamping · cohort fitness funnel ·
`missing_for_full_computability` · fail-closed disclosure · append-only audit · PS3.15 language
discipline · petition-brokering with pixels architecturally absent.

*Two agents caught the same flaw in my architecture within minutes of each other. That's the crew
working exactly as designed — and it's why we check the claim before we make it on stage.* 🔦
