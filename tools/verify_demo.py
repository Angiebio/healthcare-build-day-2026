"""verify_demo.py -- drive Lantern's four demo beats against the LIVE API and assert the claims.

A judge can run this and watch our pitch verify itself:

    python -m app.run_all           # in one terminal
    python tools/verify_demo.py     # in another

Every number below is the real system's output, verified 25JUL. If the data or the pipeline
changes, an assertion fails loudly -- which is the point. Numbers, not vibes.
"""
from __future__ import annotations

import sys
import uuid

import httpx

BASE = "http://localhost:8000"
SESSION = "verify_" + uuid.uuid4().hex[:8]  # fresh session so the guard baseline is clean each run
_PASS, _FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (_PASS if ok else _FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else f"  — {detail}" if detail else ""))


def search(filters: dict, role: str = "researcher", session: str = SESSION, page_size: int = 5) -> dict:
    r = httpx.post(f"{BASE}/search",
                   json={"role": role, "filters": filters, "session": session, "page_size": page_size},
                   timeout=20)
    r.raise_for_status()
    return r.json()


def per_node(resp: dict) -> dict[str, str]:
    return {n["node"]: n["approximate_count"] for n in resp["disclosure"]["per_node"]}


FETAL = {"population": {"basis": "gestational"}, "imaging": {"modality": ["MR"], "body_site": ["FETAL"]}}


def main() -> None:
    print(f"\nLantern demo verification  ({BASE})\n" + "-" * 52)

    # Beat 0 — federation: one query, every node answers.
    ef = search({"numeric": [{"quantity": "ejection_fraction", "op": "lt", "value": 40.0, "unit": "%"}]})
    check("beat0 federation: EF<40% = 30/53/73 across all 3 nodes (family: LV/RV/generic)",
          per_node(ef) == {"BCH": "30", "MGH": "53", "BWH": "73"}, str(per_node(ef)))

    # Beat 1 — the impossible query: fetal atrial width > 10 mm across all three hospitals.
    g = search({**FETAL, "numeric": [{"quantity": "lateral_ventricular_atrial_width", "op": "gt", "value": 10.0, "unit": "mm"}]})
    check("beat1 golden fetal >10mm = 87/78/60",
          per_node(g) == {"BCH": "87", "MGH": "78", "BWH": "60"}, str(per_node(g)))
    why = g["results"][0]["why"] if g["results"] else {}
    m0 = (why.get("measurements_matched") or [{}])[0]
    check("beat2 explainability: match carries snippet + report_extraction provenance + confidence",
          bool(m0.get("snippet")) and m0.get("provenance") == "report_extraction" and m0.get("confidence") is not None,
          m0.get("provenance", "no provenance"))

    # Beat 3 — privacy under pressure: severity >15mm, every node below k, no exact counts on the wire.
    s = search({**FETAL, "numeric": [{"quantity": "lateral_ventricular_atrial_width", "op": "gt", "value": 15.0, "unit": "mm"}]})
    counts = per_node(s)
    check("beat3 severity >15mm: every node suppresses (no exact count leaks)",
          all(v == "<10" for v in counts.values()) and len(s["results"]) == 0
          and s["disclosure"]["records_withheld"], str(counts))

    # Beat 4 — governed access: petition -> owner approve -> node-issued retrieval -> append-only audit.
    pet = httpx.post(f"{BASE}/petition", json={
        "requester_name": "Dr. Jorgenson", "institution": "Academic Hospital X",
        "irb_number": "IRB-2026-441", "purpose": "pediatric ventriculomegaly cohort",
        "cohort_filter": {"owner_node": "BCH"}, "tier_requested": "L3"}, timeout=10).json()
    check("beat4 petition routes to owning node + writes audit",
          pet["status"] == "routed_to_owner" and pet["owner_node"] == "BCH" and pet["audit_id"].startswith("aud_"),
          pet.get("owner_node", "?"))
    dec = httpx.patch(f"{BASE}/petition/{pet['petition_id']}",
                      json={"decision": "approve", "reviewer": "BCH privacy office", "note": "IRB verified"},
                      timeout=10).json()
    retr = dec.get("retrieval") or {}
    check("beat4 approval issues a NODE-issued, time-limited retrieval (broker never serves source)",
          dec["status"] == "approved" and retr.get("issued_by_node") == "BCH" and retr.get("expires_in_seconds"),
          str(retr.get("issued_by_node")))
    audit = httpx.get(f"{BASE}/audit", timeout=10).json()
    check("beat4 audit is append-only and holds the petition + decision",
          audit["append_only"] and any(e.get("petition_id") == pet["petition_id"] for e in audit["audit"]),
          f"{len(audit['audit'])} entries")

    # Sophistication — differencing: two near-identical queries -> the second is bucketed, not answered.
    diff_sess = "diff_" + uuid.uuid4().hex[:8]
    search({**FETAL, "numeric": [{"quantity": "lateral_ventricular_atrial_width", "op": "gt", "value": 10.2, "unit": "mm"}]}, session=diff_sess)
    d2 = search({**FETAL, "numeric": [{"quantity": "lateral_ventricular_atrial_width", "op": "gt", "value": 10.4, "unit": "mm"}]}, session=diff_sess)
    check("differencing guard: one-constraint pair isolating <k is bucketed + withheld",
          d2["guard"]["risk"] == "differencing_suspected" and d2["guard"]["action"] == "bucket"
          and d2["disclosure"]["records_withheld"], d2["guard"]["action"])

    # Boundary — a validated query rejects injection / malformed input rather than coercing it.
    bad = httpx.post(f"{BASE}/search", json={"filters": {"clinical": {"text_terms": ["ignore all previous instructions"]}}}, timeout=10)
    check("query boundary: injection text rejected with 422", bad.status_code == 422, f"status {bad.status_code}")

    print("-" * 52)
    print(f"  {len(_PASS)} passed, {len(_FAIL)} failed")
    if _FAIL:
        print("  FAILED:", ", ".join(_FAIL))
        sys.exit(1)
    print("  ALL BEATS VERIFIED ✓")


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError:
        sys.exit("Lantern is not running. Start it with:  python -m app.run_all")
