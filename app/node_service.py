"""Node-side compiler + search sidecar. ONE runs per hospital (BCH/MGH/BWH).

THIS IS THE TRUST BOUNDARY MADE REAL. The sidecar is the only thing that touches
the raw, PII-leaking node record. It compiles each record into a de-identified
Study Passport locally and answers queries against its OWN passports. The broker
never sees this service's raw data -- it can only reach `/search` and `/passport`,
which return compiled passports and never prose. And k-anonymity is applied HERE,
node-side: if this node's matching cohort is smaller than k, the records never
leave the building at all -- only a suppressed count crosses. That is the honest
version of "computation goes to the data."

Run:  LANTERN_NODE=BCH uvicorn app.node_service:app --port 8011
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from scripts.query_ast import QueryError, compile_query  # noqa: E402
from scripts.kanon import apply_disclosure  # noqa: E402
from app.retrieval import search as retrieval_search  # noqa: E402

NODE_CONFIG: dict[str, dict[str, Any]] = {
    "BCH": {"file": "bch_data.json", "label": "Boston Children's", "policy": "auto_approve_L1_with_irb"},
    "MGH": {"file": "mgh_data.json", "label": "Mass General", "policy": "petition_required"},
    "BWH": {"file": "bwh_data.json", "label": "Brigham & Women's", "policy": "petition_required"},
}
# Where the provided provider-node corpus lives. Override on any other machine with
# LANTERN_PROVIDER_DATA=/path/to/provider-node/data. If it's absent, the sidecar falls
# back to the committed fixtures (still de-identified) and says so in /health.source.
DATA_DIR = Path(os.environ.get("LANTERN_PROVIDER_DATA", r"C:\Users\ajohn\hackdata\provider-node\data"))

NODE = os.environ.get("LANTERN_NODE", "BCH").upper()
if NODE not in NODE_CONFIG:
    raise SystemExit(f"WIRING FAILURE: unknown LANTERN_NODE={NODE!r}; expected one of {list(NODE_CONFIG)}")

# The compiler is imported, not reimplemented -- single source of truth with the fixture press.
# When scripts/compiler.py (T-12) lands this import swaps to it and nothing else changes.
try:
    from tools.build_fixtures import compile_passport
    _HAVE_COMPILER = True
except Exception:  # noqa: BLE001 - degrade to the pre-compiled fixtures rather than fail the demo
    compile_passport = None  # type: ignore
    _HAVE_COMPILER = False


def _load_passports(node: str) -> tuple[list[dict[str, Any]], str]:
    """Compile this node's raw records locally; fall back to the pre-built fixture slice."""
    raw_file = DATA_DIR / NODE_CONFIG[node]["file"]
    if _HAVE_COMPILER and raw_file.exists():
        raw = json.loads(raw_file.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = next(v for v in raw.values() if isinstance(v, list))
        return [compile_passport(node, rec) for rec in raw], "raw+compiled(node-side)"
    fx = json.loads((REPO / "app" / "static" / "fixtures.json").read_text(encoding="utf-8"))
    return [p for p in fx["passports"] if p.get("owner", {}).get("node") == node], "fixtures-fallback"


PASSPORTS, SOURCE = _load_passports(NODE)
LABEL = NODE_CONFIG[NODE]["label"]
POLICY = NODE_CONFIG[NODE]["policy"]

app = FastAPI(title=f"Lantern node · {NODE}")


class SearchBody(BaseModel):
    filters: dict[str, Any] = {}
    layer: str = "L1"
    threshold: int = 10


@app.get("/health")
def health() -> dict[str, Any]:
    return {"node": NODE, "label": LABEL, "studies": len(PASSPORTS), "source": SOURCE, "ok": True}


@app.get("/policy")
def policy() -> dict[str, Any]:
    return {"node": NODE, "label": LABEL, "policy": POLICY}


@app.post("/search")
def search(body: SearchBody) -> dict[str, Any]:
    try:
        ast = compile_query(None, body.filters)
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    matches = retrieval_search(ast, PASSPORTS)
    # k-anon fires NODE-SIDE: a sub-threshold cohort's records never leave this service.
    disc = apply_disclosure(matches, threshold=body.threshold, layer=body.layer)
    d = disc.to_dict()
    records = d.pop("records")  # sent as `matches`; never duplicated into disclosure
    return {
        "node": NODE, "label": LABEL, "policy": POLICY,
        "disclosure": d,                       # count_suppressed, approximate_count, k_anon_ok, threshold, ...
        "candidate_count": len(matches) if disc.k_anon_ok else None,  # None when suppressed -> nothing to difference
        "matches": records,                    # [] when suppressed
    }


@app.get("/passport/{study_id}")
def passport(study_id: str) -> dict[str, Any]:
    pid = f"{NODE.lower()}:{study_id}"
    for p in PASSPORTS:
        if p.get("passport_id") == pid or p.get("passport_id", "").split(":")[-1] == study_id:
            return p
    raise HTTPException(status_code=404, detail=f"no passport {study_id} at {NODE}")
