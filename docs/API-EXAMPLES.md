# Lantern — copy-paste request bodies for every demo beat
> These are the **exact** bodies `tools/verify_demo.py` sends and that return 200. If a request
> 422s, it's one of the three gotchas below — the validator rejects rather than silently weakening a
> query, because a dropped filter is a privacy failure, not a UX convenience.

## Why a search 422s (read this first — it's the whole gap)
1. **Fetal queries MUST set `population.basis: "gestational"`.** `PatientAge` on a fetal record is the
   *mother's* age, so the system refuses to treat a fetus chronologically. `body_site:["FETAL"]`
   without `population.basis:"gestational"` → 422.
2. **`modality` and `body_site` are LISTS, not strings.** `"MR"` → 422; `["MR"]` → OK.
3. **Every numeric constraint needs its canonical `unit`.** atrial width → `"mm"`, EF → `"%"`,
   gestational age → `"weeks"`, chamber volume → `"mL"`. Missing/incorrect unit → 422.

Start the stack: `python -m app.run_all` (broker on :8000). All examples POST to `http://localhost:8000`.

---

## Beat 0 — federation (EF < 40%, every node answers · 30 / 53 / 73)
`ejection_fraction` matches the whole family (LV + RV + generic).
```bash
curl -s localhost:8000/search -H "content-type: application/json" -d '{
  "role": "researcher",
  "filters": { "numeric": [ {"quantity":"ejection_fraction","op":"lt","value":40,"unit":"%"} ] }
}'
```

## Beat 1 — the impossible query (fetal atrial width > 10 mm · 87 / 78 / 60)  ★
```bash
curl -s localhost:8000/search -H "content-type: application/json" -d '{
  "role": "researcher",
  "filters": {
    "population": { "basis": "gestational" },
    "imaging":    { "modality": ["MR"], "body_site": ["FETAL"] },
    "numeric":    [ {"quantity":"lateral_ventricular_atrial_width","op":"gt","value":10,"unit":"mm"} ]
  }
}'
```
Read `results[].why` for the reason string, matched value, confidence, provenance, and the source snippet.

## Beat 3 — privacy under pressure (severity > 15 mm · every node suppresses)  ★
```bash
curl -s localhost:8000/search -H "content-type: application/json" -d '{
  "role": "researcher",
  "filters": {
    "population": { "basis": "gestational" },
    "imaging":    { "modality": ["MR"], "body_site": ["FETAL"] },
    "numeric":    [ {"quantity":"lateral_ventricular_atrial_width","op":"gt","value":15,"unit":"mm"} ]
  }
}'
```
Expect `results: []`, `disclosure.records_withheld: true`, every `per_node.approximate_count: "<10"`.
The exact count is **absent from the response**, not hidden in the UI.

## Differencing defense (run both on the SAME session; the 2nd is bucketed)
```bash
curl -s localhost:8000/search -d '{"session":"atk","filters":{"population":{"basis":"gestational"},"imaging":{"modality":["MR"],"body_site":["FETAL"]},"numeric":[{"quantity":"lateral_ventricular_atrial_width","op":"gt","value":10.2,"unit":"mm"}]}}' -H "content-type: application/json"
curl -s localhost:8000/search -d '{"session":"atk","filters":{"population":{"basis":"gestational"},"imaging":{"modality":["MR"],"body_site":["FETAL"]},"numeric":[{"quantity":"lateral_ventricular_atrial_width","op":"gt","value":10.4,"unit":"mm"}]}}' -H "content-type: application/json"
```
2nd response: `guard.risk:"differencing_suspected"`, `guard.action:"bucket"`, records withheld.

## Beat 4 — governed access (petition → approve → node-issued retrieval → audit)
```bash
# 1) petition  -> returns petition_id + audit_id, routed to the owning node
curl -s localhost:8000/petition -H "content-type: application/json" -d '{
  "requester_name":"Dr. Jorgenson","institution":"Academic Hospital X",
  "irb_number":"IRB-2026-441","purpose":"pediatric ventriculomegaly cohort",
  "cohort_filter":{"owner_node":"BCH"},"tier_requested":"L3" }'

# 2) owner approves (use the petition_id from step 1) -> node-issued, time-limited retrieval
curl -s -X PATCH localhost:8000/petition/<PETITION_ID> -H "content-type: application/json" \
  -d '{"decision":"approve","reviewer":"BCH privacy office","note":"IRB verified"}'

# 3) append-only audit trail
curl -s localhost:8000/audit
```

## Other endpoints
```bash
curl -s localhost:8000/nodes                         # per-node health, study counts, policy
curl -s "localhost:8000/passport/BCH/FT-4113?role=researcher"   # full L1 passport + de-id manifest
curl -s "localhost:8000/passport/BCH/FT-4113?role=patient"      # L0: existence + plain language only
```

## Roles (server-side, never client-trusted)
`role: "researcher"` → L1 (full passport) · `"clinician"` → L2 (+ owner contact) · `"patient"` → L0
(codes + cohort existence, **no values, no snippets**). The UI switcher is a demo identity; the
server still redacts.
