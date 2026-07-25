# Why this is actually novel
> Talking points for the pitch, the video, and champion Q&A. Read on a phone.
> Every claim here is backed by something in the repo. Nothing is hype.

---

## The one-sentence version

> **Most privacy engineering asks "how much can we degrade this data and keep it useful?"
> We asked "what if we compute the useful thing while we still lawfully hold the sensitive thing,
> and then throw the sensitive thing away?"**

That is not a better point on the privacy-utility tradeoff curve. It steps off the curve. Utility
goes **up** while exposure goes **down**, which is not supposed to be possible, and the reason it
works here is ordering: we compute **before** we discard, not after.

---

## 1. We made a search axis that does not exist in any product

**The fact:** 78.4% of the radiology reports in this corpus contain quantitative clinical
measurements written into the prose. Ventricular widths in millimetres. Ejection fractions.
Gestational age.

**The bind:** those numbers are simultaneously the most scientifically valuable content in the record
and the most dangerous to release, because free text is where identity hides. So today they are both
unsearchable and unshippable.

**What we did:** compile them into typed, queryable facts inside the hospital, index the facts,
release none of the report.

**Say this:** *"Today you can search 'fetal MRI'. You cannot search 'atrial width over 10 millimetres'.
A radiologist already measured it. It is sitting in sentence three, where no query can reach it and no
privacy office can release it."*

**And the kicker:** 10 mm is not a number we invented for a demo. It is the diagnostic threshold for
fetal ventriculomegaly. We are not making up a query. We are making a real clinical question
answerable across institutions for the first time.

---

## 2. A technical finding we did not expect, and have not seen elsewhere

**Disclosure risk belongs to a hospital, not to the federation.**

Everyone applies k-anonymity per node. Almost nobody notices that the **differencing defence must
also be per node.**

Here is the actual case, from our own data:
- Two queries differing by one constraint isolate **9 studies at Boston Children's**. That is below
  our threshold of 10. It is a leak.
- Summed across all three hospitals, the same pair differs by **17**. Comfortably safe.

**Assessed federation-wide, the attack succeeds. Assessed per hospital, it is caught.**

We found this live, against real numbers, and rebuilt the guard to hold a separate query ledger per
institution. A node whose own ledger trips gets degraded to count bands while its safer peers still
return records.

**Say this:** *"A safe network total can hide an unsafe hospital delta. That asymmetry is the
federation being real rather than three databases in a trenchcoat."*

---

## 3. The dangerous capability is absent, not forbidden

We do not serve source images. Not because a policy says no, but because **there is no code path that
could.** The broker has no import, no route, and no address that reaches raw data, and a test proves
it rather than a document asserting it.

**Say this:** *"You cannot misuse a capability the system does not have. We broker the request and
route it to you. We never hold the pixels, so we cannot leak them."*

---

## 4. A machine's guess never wears a clinical fact's clothes

Every extracted number carries three things: where it came from, how confident the extractor was, and
**the exact sentence it was taken from.**

In clinical research the difference between a documented finding and a software inference is the
difference between evidence and a hypothesis. A system that blurs them produces results nobody should
act on. Because the source phrase travels with the number, a clinician can adjudicate any single value
in about two seconds.

**Say this:** *"That is what makes an extracted axis usable rather than merely impressive."*

---

## 5. We measured ourselves against the naive baseline, and published a loss

We built the keyword search a hospital has today, ran it on the same corpus, and reported the
comparison.

- Keyword search for **"severe ventriculomegaly"** returns 29 hits at Boston Children's. **Seven are
  real.** 24% precision.
- For threshold queries we report the baseline as **"not expressible"** rather than as recall zero.
  A keyword search does not perform *badly* at ordering a measurement. It cannot express the question.
- **Our own evaluation records a case where plain keyword matching beats our ontology expansion on
  precision. We left it in.**

**Say this:** *"A comparison that only flatters its author is not a measurement."*

---

## 6. The honest inventory

Every passport carries a field listing **what this data cannot support.** For this corpus that
includes acquisition parameters and pixel data, because the corpus has neither.

We also publish a page recording where we were wrong: a demonstration query that returned zero rows
until we checked it, and a bug where fetal studies were being aged by the **mother's** age, which
would have rendered a fetus as an adult.

**Say this:** *"A researcher deciding whether to spend six months on a cohort is better served by an
accurate inventory than an impressive one. Naming the gap is what separates a research instrument
from a demo."*

---

## If you only remember three things

1. **We compute before we discard, so utility rises while exposure falls.** That ordering is the
   whole invention.
2. **Disclosure risk is per hospital, not per network** — and we can show the exact query pair that
   proves it.
3. **We published our own failures and a benchmark we lose.** In a room full of privacy claims, the
   team that names its limits is the one to believe.

---

## Two things never to say
- **"HIPAA compliant."** Safe Harbor and Expert Determination are the only two routes and we drove
  neither. Say *PS3.15-inspired field minimization with policy-gated release evidence.*
- **"Differential privacy."** We do k-anonymity and count bands. Say that.
