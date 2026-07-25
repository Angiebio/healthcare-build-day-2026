# 🔒 FROZEN API CONTRACT — Lantern
> **Frozen 25JUL2026 by Flame-Fable. Changes require dispatch sign-off and a shout to the room.**
> Frontend builds against this immediately and does not wait for the backend to exist.
> Every endpoint returns JSON. Every list endpoint is explainable. Every denial is legible.

> **⚠️ AMENDED 25JUL post-red-team — see `07-CORRECTIONS-v2.md`.** The compiler now runs in a
> **node-side sidecar** (:8011/8012/8013), not in the broker. The broker federates over sidecars only
> and must have no import or route reaching raw `/api/studies`. `PATCH /petition/{id}` is replaced by
> **`POST /petition/{id}/decision`** (append-only semantics). Approval must issue a **node-issued,
> time-limited retrieval** — routing alone doesn't satisfy the challenge's requirement #4.

## Upstream (given, do not modify) — the 3 hospital nodes
`GET http://localhost:{8001|8002|8003}/api/studies` · `/api/studies/{study_id}` · `/health`
Nodes are dumb, unauthenticated, and leak PII **on purpose**. Ours is the layer that fixes that.
Node map: `8001=BCH (pediatric)`, `8002=MGH (adult)`, `8003=BWH (adult)`.

## Our API (`app/`, FastAPI, port 8000)

```http
GET  /                  the researcher console (static SPA). The UI is served by the broker
                        itself, so :8000 is the only port a demo needs.

POST /search
  body: { text?: str, filters?: {...}, role: "researcher"|"clinician"|"patient",
          session?: str, page?, page_size? }
  → { query_ast, results, disclosure, guard, nodes_queried, page, page_size, timing_ms }
  ⚠️ `total_before_suppression` REMOVED (25JUL, red team). Returning an exact pre-suppression count
  alongside a suppressed cohort defeats k-anonymity. When suppression fires, return ONLY the bucket.
  Each result is { passport, node, why } — `why` = {signals_fired, reason_text, measurements_matched}
  Per-node disclosure lives at `disclosure.per_node[]`; `nodes_queried` is a list of node NAMES.
  `session` scopes the differencing guard. Queries sharing a session are compared against each
  other; omit it and everything lands in one shared bucket, which will produce spurious
  differencing warnings during a scripted demo. **Send a fresh session per unrelated query.**

GET  /passport/{node}/{study_id}
  → full Tier-appropriate Passport (see §Passport). Never the full report. Never pixels.
     Carries a bounded evidence snippet per measurement, `deid_manifest`, and per-field `provenance`.

POST /petition
  body: { requester_name, institution, irb_number, purpose, cohort_filter, tier_requested }
  → { petition_id, status: "routed_to_owner", owner_node, owner_contact, audit_id, timestamp }
  Side effect: append-only audit write. This is the ONLY path toward source data.

POST /petition/{id}/decision   body: { decision: "approve"|"deny", reviewer, note }  (owner view)
  Appends a decision EVENT; it never mutates the original petition. POST, not PATCH — the verb
  should say "append", because that is what the audit guarantees.
GET  /petitions         (owner view — pending queue)
GET  /audit             append-only trail, newest first. Never mutable.
GET  /nodes             → { nodes: [{node,label,studies,policy,reachable,...}], k_anon_threshold }
                        NOTE: an object, not a bare array.

GET  /cohort            ❌ NOT IMPLEMENTED — returns 400 by design.
                        Cohort counts come from `POST /search` → read `disclosure`. A separate
                        count endpoint is a differencing gift: it hands out cohort sizes without
                        the guard that watches how they are being asked for. Kept in the doc as a
                        deliberate refusal rather than deleted, so nobody re-adds it.
```

### Passport (the artifact — L1 researcher view)
```json
{"passport_id":"bch:BR-1543","owner":{"node":"BCH","request_route":"/petition"},
 "imaging":{"modality":"MR","body_site":{"system":"SCT","code":"12738006","display":"Brain"},
            "body_part_raw":"BRAIN"},
 "population":{"pediatric_stage":"neonate","public_age_band":"0-1","sex":"M"},
 "measurements":[{"quantity":"lateral_ventricular_atrial_width","value":12.4,"unit":"mm",
                  "laterality":"left","confidence":0.9,"provenance":"report_extraction",
                  "snippet":"...atrial width of 12.4 mm..."}],
 "concepts":[{"system":"SCT","code":"...","display":"Cerebral infarction",
              "provenance":"report_extraction","confidence":0.86}],
 "temporal":{"study_interval_days":null,"date_shifted":true},
 "privacy":{"highest_release_layer":"L1","patient_identity_removed":true,
            "release_status":"CONTROLLED_DERIVATIVE","free_text_released":false},
 "deid_manifest":{"removed":["PatientName","PatientID","PatientBirthDate","InstitutionName"],
                  "generalized":["PatientAge→band","StudyDate→shifted"],
                  "hashed":["StudyInstanceUID"],"prose_withheld":true},
 "provenance":{"pipeline_version":"0.1.0","source_hash":"sha256:..."}}
```
**Field rule:** anything sourced from the report carries `provenance:"report_extraction"` + confidence.
Anything from a DICOM field carries `native_tag`. A model guess must never wear a clinical fact's clothes.

### Disclosure object (returned on every search)
```json
{"k_anon_ok": false, "threshold": 10, "approximate_count": "<10",
 "records_withheld": true, "reason": "cohort smaller than k-anonymity threshold",
 "petition_route": "/petition"}
```

### Role → tier mapping (server-side, never client-trusted)
`patient→L0` · `researcher→L1` · `clinician→L2` · nothing maps to L3, ever. The role switcher in the
UI is a **demo identity** with a visible banner; the server still enforces field redaction per role.

## Rules for implementers
- **Fail closed.** Exception in policy code → suppress, don't serve.
- Audit is append-only: no update, no delete paths exist in code.
- k-anon threshold is config, echoed in every response.
- Compiler runs node-side conceptually — keep PHI handling structurally isolated in `scripts/compiler.py`;
  the serving layer must never import a function that can see raw prose. **Jim verifies this claim.**
