# Demo-script sign-off — Pooja Upadhyay (QARA), 12:49 PM
> The four open questions in `demo-script.md`, answered by our regulatory authority in the room.
> These are final; `demo-script.md` has been updated to match. Only a champion contradiction in
> office hours (which outranks the script) changes anything below.

## 1. Opening register (0:00–0:18) — KEEP AS-IS
Reads as the family's / clinician's problem, not an engineer's. No jargon, centers the wait, earns
the emotional credit before beat 1a turns technical. **No change.**

## 2. Privacy sentence (1:15) — CHANGED (register, not meaning)
"No hospital will disclose its own count" reads as *institutional discretion* — a hospital choosing
silence. What's actually happening is stronger and more auditable: **k-anonymity suppression,
threshold = 10, config-surfaced, fail-closed** (confirmed `docs/API-CONTRACT.md` — an exception in
policy code suppresses, never serves). Say the true thing.

**Video script copy (shorter, fits the 2-min budget — now in `demo-script.md`):**
> "Below ten, the policy engine won't release a count — the rule is fail-closed, it fires the same
> way every time, no exceptions. You get a band, never a number. That's the disclosure boundary — the
> hospital's, not a central system's. That's federation, not a warehouse with a login."

**Live-pitch / Q&A copy (fuller — use when time allows, e.g. the 3-min live pitch):**
> "Below ten, the policy engine won't release an exact count — not because a hospital chooses silence,
> but because the rule fires automatically, every time, and fails closed: if anything ever goes wrong
> in that code path, it suppresses, it never serves. You get a band, never a number. Sixteen studies
> exist across the network — enough to clear the threshold together — but no single hospital's small
> cohort is ever exposed. That's the disclosure boundary. That's what makes this federation, and not a
> warehouse with a login."

## 3. Narrator for beat 3 — POOJA DELIVERS IT
Criterion 3 comes from an actual QARA authority in the room, not an engineer reading a line. Real
points with judges who know the difference. `demo-script.md` beat 3 is marked **[narrator: Pooja]**.

## 4. Champion contradictions — NONE YET
Pooja will flag immediately after office hours if anything the champion says conflicts with a line —
per the standing rule that the champion outranks the script.
