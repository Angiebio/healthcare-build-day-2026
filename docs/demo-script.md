# 🎬 Lantern — 2-minute demo video script
> Flame2, 25JUL2026 12:55 · **v1 for Angie + Pooja to react to before 1:00 office hours.**
> Every number here is asserted green in `tests/test_demo_ladder.py` + `tools/verify_console.mjs`.
> Timings are read-aloud tested at a calm pace. Total **1:58**.

**Mark up anything that sounds wrong to you and leave it on the table — I'll cut v2 by 1:45.**
The two things only you two can judge: **(a)** does the opening line sound like a clinician's
problem or an engineer's problem, and **(b)** is the privacy language exactly right.

---

## The shape (why it's in this order)

We answer **their** question before showing off ours. The challenge brief's requirement #1
is semantic diversity, so that goes first, plainly. Then the thing nobody else can do. Then
privacy holding under pressure. Then governed access. Problem → their ask → our wow →
the hard part → the close.

---

## 0:00–0:18 · The problem, in the champion's words

> **[screen: the console, already loaded, nothing typed yet]**
>
> "A child has a brain MRI every few months while a family waits to find out if a tumour
> has grown. To build tools that read those scans reliably, researchers need examples from
> many children, many scanners, many hospitals.
>
> Those scans exist. But a researcher can spend *months* — contacting hospitals one at a
> time, describing a study — just to find out whether enough data exists at all. Not to get
> it. To find out if it's there."

*(18s. Angie: this is the beat where you sound like you've watched it happen. Slow down.)*

## 0:18–0:35 · Beat 1a — the thing they asked for

> **[click "1a pediatric brain tumour"]**
>
> "So: search the network for *pediatric brain tumour*.
>
> Hospitals don't use the same words. One writes 'tumour', another 'neoplasm', another
> 'glioma'. Lantern expands the question once, centrally — **[point at the expansion strip]**
> — so every hospital answers the question we actually meant, in its own vocabulary."

*(17s. This is requirement #1 of their brief, answered in one screen. Don't rush past it —
some teams will skip this entirely and it's literally the first thing the champion asked for.)*

## 0:35–0:52 · Beat 1b — federation, working

> **[click "1b ejection fraction < 40%"]**
>
> "Now something no catalogue can answer today: every study where the **measured ejection
> fraction is under forty percent** — the clinical threshold for reduced heart function.
>
> **Thirty at Boston Children's. Fifty-three at Mass General. Seventy-three at the
> Brigham.** Three hospitals, three separate services, one question."

*(17s. Numbers verified: 30 / 53 / 73.)*

## 0:52–1:15 · Beat 2 — the impossible query ★

> **[click "2 atrial width > 10 mm"]**
>
> "Here's the one I'd point at. Fetal MR where the **lateral ventricular atrial width is
> over ten millimetres** — that's the textbook definition of fetal ventriculomegaly.
>
> **Eighty-seven, seventy-eight, sixty.** Two hundred and twenty-five studies.
>
> That number was never in a database field. A radiologist wrote it in a sentence, and
> until now it was invisible to search and too risky to share. We compile it into a fact
> *inside the hospital* and index the fact — **the report itself never leaves.**"
>
> **[click the first table row — `bch:FT-3091`]**
>
> "And every fact shows its work: the value, the confidence, and **the clause it was read
> from** — enough to check the number, not the narrative around it. Left and right, parsed
> separately. A model's guess never gets to wear a clinical fact's clothes."

*(23s. THE beat. Verified 87 / 78 / 60 = 225. First row is deterministic and bilateral —
`right 18.2 mm` / `left 17.9 mm` — which proves the parser isn't naive, and that detail is
what a radiologist will notice.)*

> ⚠️ **Do not say "we never release the sentence."** We do release a bounded evidence
> snippet, deliberately, because an untraceable measurement is not a scientific claim. The
> honest line — *"the report never leaves; the clause that justifies the number does"* — is
> both true and stronger, and it survives the follow-up question. Overclaiming here is the
> single easiest way to be caught by someone who then opens a passport and reads one.

## 1:15–1:38 · Beat 3 — privacy holding under pressure ★

> **[click "3 severe > 15 mm"]**
>
> "Now narrow to severe — over fifteen millimetres.
>
> **Every hospital goes dark.** Each one holds fewer than ten matching studies, and below
> that threshold no hospital will disclose its own count. You get a band, not a number —
> and the exact count isn't hidden in the interface, it is **absent from the response**.
>
> Note *where* that decision was made. Sixteen studies exist across the network, which
> would clear the threshold — but no single hospital may expose its own small cohort. The
> hospital is the disclosure boundary. That's what makes this federation and not a
> warehouse with a login."

*(23s. Verified: 7 / 6 / 3, all suppressing. This is the criterion-3 beat — the one that
makes a privacy officer relax. Pooja: is "no hospital will disclose its own count" the
right register, or too casual?)*

## 1:38–1:52 · Beat 4 — governed access

> **[click "Petition the owning hospitals" → submit → receipt]**
>
> "When suppression is the right answer, the researcher isn't stuck — they petition. It
> routes to the owning hospital with IRB and purpose attached, and writes an
> **append-only audit entry**.
>
> We never held the scan. We brokered the request."

*(14s.)*

## 1:52–1:58 · Close

> "Existing systems ask *may I have the scan?*
>
> Lantern asks **what does the scan already know — and how much of that can you have right
> now, without the scan moving at all?**"

*(6s.)*

---

## Language discipline — the one way we lose the room

Say, verbatim:
- ✅ "PS3.15-**aligned** de-identification with policy-gated release evidence"
- ✅ "Synthetic challenge data. We touched no real PHI, deliberately, on day one."
- ✅ "Measurements are extracted with stated confidence and provenance — **not clinically validated**."
- ✅ "Three real services on one laptop. Real fan-out, honest scaffolding."

Never:
- ❌ "HIPAA compliant" — Safe Harbor and Expert Determination are the only two roads and we
  drove neither. A sharp judge pounces and they'd be right.
- ❌ "differential privacy" — we do k-anonymity and count buckets. Say that.
- ❌ "BCH is purely pediatric" — this corpus has BCH records to 35y. Say "pediatric-focused."

## Recording notes

- **Window:** browser only, 1920×1080, console at `http://localhost:8000/`.
- **Zoom to ~125%** before recording. Judges may watch this on a laptop.
- Demo-ladder buttons are in the left rail, in order — **no typing on camera**, nothing to fumble.
- The console boots already on beat 2, so hit "1a" first to start clean.
- Win+Alt+R to capture. **Do one silent dry run** — the click path is the risky part, not the words.
- If we run long, the cut is the second half of 0:00–0:18. Never cut beat 3.

## Open questions for Angie + Pooja *(answer before 1:00 if you can)*

1. **Opening register** — does 0:00–0:18 sound like a clinician's problem or an engineer's?
   It's the only bit of the script that has to earn emotional credit.
2. **Pooja — the privacy sentence at 1:15.** "No hospital will disclose its own count."
   Accurate? Too casual? What would your privacy office actually say?
3. **Who narrates?** Written in Angie's voice. If Pooja takes beat 3, criterion 3 gets
   delivered by an actual QARA authority — which is worth real points.
4. **Anything the champion says in office hours** that contradicts a line here — that
   outranks the script. Bring it back and I'll recut.
