# 🎬 RUNSHEET — record the 2-minute demo cold
> Flame2, 25JUL2026 14:05. **No rehearsal needed. Follow the numbers.**
> Companion to `docs/demo-script.md` (the prose). This is the keyboard version.
> Every number below was verified live at 14:00 by `node tools/verify_live.mjs`.

**You need:** this page open on a phone or second screen, and the browser. Nothing else.
**Total runtime:** 1:58. **If you fluff a line, keep going** — we cut once, not per-beat.

---

# ① PRE-FLIGHT — 60 seconds, do not skip

Open a terminal in the repo and run **one** command:

```
node tools/verify_live.mjs
```

**You want to see exactly this:**
```
  PASS  beat 2  fetal atrial width > 10mm      {"BCH":87,"MGH":78,"BWH":60}
  PASS  beat 3  severe > 15mm  (all suppress)  {"BCH":"<10","MGH":"<10","BWH":"<10"}
  PASS  beat 1b  EF < 40%                      {"BCH":30,"MGH":53,"BWH":73}
  live chain verified
```

| If you see | Do this |
|---|---|
| `live chain verified` | ✅ Go to ②. |
| `BROKER DOWN` | Run `python -m run_demo` (or ask Flame1). Wait 15s, re-run. |
| any `FAIL` with different numbers | **STOP. Get Flame2 or Flame-Fable.** Do not record wrong numbers. |

Then open the console and leave it open:
```
http://127.0.0.1:8080/app/static/index.html
```
Top-right of the grey stripe should read **`source: live broker :8000 · 3/3 nodes reachable`**.
If it says *local fixtures*, the broker isn't up — the demo still works, but say nothing about
"three services" and fix it if you can.

# ② SCREEN SETUP — 30 seconds

1. **Close every other tab.** No bookmarks bar, no notifications.
2. **Ctrl + `+`** until the browser reads **125%** (three presses from default).
3. **F11** for full screen. *(Optional but it looks much better.)*
4. Click **`1a  pediatric brain tumour`** in the left rail — this parks you at the start.
5. **Win + Alt + R** to start recording. Wait 2 seconds before speaking.

> The four ladder buttons are at the **bottom of the left rail**, labelled `1a`, `1b`, `2`, `3`.
> **You never type anything on camera.** Every beat is one click.

---

# ③ THE TAKE

Read the **SAY** column. Do the **DO** column. Glance at **SEE** to confirm you're on track.

---

### 0:00 – 0:18 · The problem

**DO** — nothing. Console sits still on the 1a screen.

**SAY**
> "A child has a brain MRI every few months while a family waits to find out if a tumour has
> grown. To build tools that read those scans reliably, researchers need examples from many
> children, many scanners, many hospitals.
>
> Those scans exist. But a researcher can spend *months* — contacting hospitals one at a time,
> describing a study — just to find out whether enough data exists at all. Not to get it. To
> find out if it's there."

**SEE** — static screen. *Slow down here. This is the only part that has to land emotionally.*

---

### 0:18 – 0:35 · Beat 1a — the thing they asked for

**DO** — click **`1a  pediatric brain tumour`**.

**SAY**
> "So: search the network for *pediatric brain tumour*.
>
> Hospitals don't use the same words. One writes 'tumour', another 'neoplasm', another 'glioma'.
> Lantern expands the question once, centrally — so every hospital answers the question we
> actually meant, in its own vocabulary."

**SEE** — a purple-edged **callout box** appears above the results reading *"Semantic expansion
fired: tumor → …"* with word chips. **Point the cursor at it while you say "expands the question."**

---

### 0:35 – 0:52 · Beat 1b — federation working

**DO** — click **`1b  ejection fraction < 40%`**.

**SAY**
> "Now something no catalogue can answer today: every study where the **measured ejection
> fraction is under forty percent** — the clinical threshold for reduced heart function.
>
> Thirty at Boston Children's. Fifty-three at Mass General. Seventy-three at the Brigham.
> Three hospitals, three separate services, one question."

**SEE** — three node chips across the top: **BCH 30 · MGH 53 · BWH 73**.
⚠️ **If those numbers differ, stop the recording and get Flame2.**

---

### 0:52 – 1:15 · Beat 2 — the impossible query ★

**DO** — click **`2  atrial width > 10 mm`**. Then **click the first row of the table**.

**SAY** *(first half, before clicking the row)*
> "Here's the one I'd point at. Fetal MR where the **lateral ventricular atrial width is over
> ten millimetres** — that's the textbook definition of fetal ventriculomegaly.
>
> Eighty-seven, seventy-eight, sixty. Two hundred and twenty-five studies.
>
> That number was never in a database field. A radiologist wrote it in a sentence, and until
> now it was invisible to search and too risky to share. We compile it into a fact *inside the
> hospital*, index the fact, and never release the sentence."

**DO** — now click the **first table row** (`bch:FT-3091`).

**SAY** *(second half, panel open)*
> "And every fact shows its work: the value, the confidence, and the exact sentence it came
> from. Left and right, parsed separately. A model's guess never gets to wear a clinical fact's
> clothes."

**SEE** — node chips **BCH 87 · MGH 78 · BWH 60**. Panel slides in from the right showing
**two** atrial-width measurements: `right 18.2 mm` and `left 17.9 mm`, each with a confidence
of 0.96 and an italic quoted snippet. **That bilateral pair is the money shot — let it sit on
screen for a beat.**

**DO** — press **Esc** to close the panel.

---

### 1:15 – 1:38 · Beat 3 — privacy holding ★

**DO** — click **`3  severe > 15 mm`**.

**SAY**
> "Now narrow to severe — over fifteen millimetres.
>
> Every hospital goes dark. Each one holds fewer than ten matching studies, and below that
> threshold no hospital will disclose its own count. You get a band, not a number — and the
> exact count isn't hidden in the interface, it is **absent from the response**.
>
> Note *where* that decision was made. Sixteen studies exist across the network, which would
> clear the threshold — but no single hospital may expose its own small cohort. The hospital is
> the disclosure boundary. That's what makes this federation and not a warehouse with a login."

**SEE** — all three node chips turn **red** and read **`<10`**. A red-edged banner appears:
*"Records withheld at 3 of 3 hospitals."* Table is empty.

---

### 1:38 – 1:52 · Beat 4 — governed access

**DO** — click **`Petition the owning hospitals`** (the button inside the red banner).
Then click **`Submit petition`**. *(The form is pre-filled — change nothing.)*

**SAY**
> "When suppression is the right answer, the researcher isn't stuck — they petition. It routes
> to the owning hospital with IRB and purpose attached, and writes an append-only audit entry.
>
> We never held the scan. We brokered the request."

**SEE** — a green-edged receipt with **`audit aud_…`** in green. *Pause on it for one second.*

---

### 1:52 – 1:58 · Close

**DO** — nothing.

**SAY**
> "Existing systems ask *may I have the scan?*
>
> Lantern asks **what does the scan already know — and how much of that can you have right now,
> without the scan moving at all?**"

**DO** — **Win + Alt + R** to stop recording.

---

# ④ IF SOMETHING GOES WRONG MID-TAKE

| Problem | Fix, live |
|---|---|
| Panel won't close | Press **Esc**. Always works. |
| Wrong beat clicked | Click the right one. Don't apologise on tape — just continue. |
| Numbers look wrong | **Stop. Re-run pre-flight.** Never narrate numbers you can see are wrong. |
| A node chip says `unreachable` | Say *"one hospital is offline and the search degrades honestly"* — that's a real feature, not a failure. |
| Red "Query refused" box | You typed in the NL box. Clear it, click the ladder button again. |
| You run long | Cut the second half of the 0:00 problem statement. **Never cut beat 3.** |

# ⑤ AFTER THE TAKE

1. Video lands in **`C:\Users\ajohn\Videos\Captures\`**.
2. Watch it once at 2× — check the audio exists and beats 1b/2/3 numbers are legible.
3. Under 2:00? ✅ Ship it. Over? Re-record; the problem statement is the only fat.
4. Put the link in the README and tell dispatch.

---

## The three numbers that must be right

If you remember nothing else, these are what a judge will check:

| Beat | On screen |
|---|---|
| 1b · EF < 40% | **30 · 53 · 73** |
| 2 · atrial width > 10 mm | **87 · 78 · 60** (225 total) |
| 3 · severe > 15 mm | **`<10` · `<10` · `<10`** — all suppressed |

## Never say these words

- ❌ "HIPAA compliant" → ✅ "PS3.15-**aligned**, with policy-gated release evidence"
- ❌ "differential privacy" → ✅ "k-anonymity with count buckets"
- ❌ "BCH is purely pediatric" → ✅ "pediatric-focused"

*The click path has been run end to end and every number verified live. Go get it. 🔦*
