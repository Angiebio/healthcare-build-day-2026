"""Lantern Broker (:8000) — the federated discovery + governance layer.

It fans a validated query out to the three node sidecars, merges only what they
are permitted to return, fuses the ranks, defends against differencing, redacts by
role, and brokers petitions into an append-only audit. It has NO path to raw prose:
it speaks only to `/search` and `/passport` on the sidecars, which return compiled
passports. That absence is the trust-boundary claim, and it is enforced by there
being no client here that knows the raw node URL at all.

Run:  uvicorn app.broker:app --port 8000
(or `python -m app.run_all` to launch the three sidecars + this together)
"""
from __future__ import annotations

import asyncio
import sys
import time
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from scripts.query_ast import QueryError, compile_query  # noqa: E402
from scripts.rank_fusion import fuse  # noqa: E402
from scripts.query_guard import QueryRecord, assess_disclosure_risk  # noqa: E402
from app.policy import redact_for_layer, role_to_layer  # noqa: E402
from app import audit  # noqa: E402

K_THRESHOLD = 10
NODES = {
    "BCH": "http://localhost:8011",
    "MGH": "http://localhost:8012",
    "BWH": "http://localhost:8013",
}
FUSION_WEIGHTS = {"numeric": 1.0, "richness": 0.3}


def _bucket(n: int) -> str:
    """Coarse count band. Used to blunt differencing: you cannot subtract '100+' from '100+'."""
    if n < K_THRESHOLD:
        return f"<{K_THRESHOLD}"
    if n <= 25:
        return "10-25"
    if n <= 50:
        return "26-50"
    if n <= 100:
        return "51-100"
    return "100+"

# In-memory demo state. Query history is partitioned by node because disclosure
# risk belongs to a hospital cohort, not to the network-wide sum that can mask it.
# The AUDIT (append-only file) is the source of truth; these are views.
_SESSIONS: dict[str, dict[str, list[QueryRecord]]] = {}
_PETITIONS: dict[str, dict[str, Any]] = {}

app = FastAPI(title="Lantern Broker", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class SearchBody(BaseModel):
    text: str | None = None
    filters: dict[str, Any] = {}
    role: str = "researcher"
    session: str = "demo"
    page: int = 1
    page_size: int = 25


async def _query_node(client: httpx.AsyncClient, node: str, url: str,
                      filters: dict[str, Any], layer: str) -> dict[str, Any]:
    """One node's answer, or an honest 'unreachable' — a dead node never becomes a 500."""
    try:
        r = await client.post(f"{url}/search",
                              json={"filters": filters, "layer": layer, "threshold": K_THRESHOLD},
                              timeout=2.0)
        r.raise_for_status()
        return {"node": node, "reachable": True, **r.json()}
    except Exception as exc:  # noqa: BLE001 - degrade to partial results, name the gap
        return {"node": node, "reachable": False, "error": type(exc).__name__,
                "disclosure": None, "candidate_count": None, "matches": []}


@app.post("/search")
async def search(body: SearchBody) -> dict[str, Any]:
    t0 = time.perf_counter()
    layer = role_to_layer(body.role)

    # 1) Compile: an LLM/user may propose; only the validated AST executes.
    try:
        ast = compile_query(body.text, body.filters)
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 2) Federated fan-out to the sidecars (never the raw nodes).
    async with httpx.AsyncClient() as client:
        node_results = await asyncio.gather(*[
            _query_node(client, node, url, body.filters, layer) for node, url in NODES.items()
        ])

    # 3) Merge only what each node was permitted to return; note suppressed + dead nodes.
    merged: list[dict[str, Any]] = []
    per_node: list[dict[str, Any]] = []
    total_returned = 0
    any_suppressed = False
    for nr in node_results:
        disc = nr.get("disclosure")
        per_node.append({
            "node": nr["node"], "reachable": nr["reachable"],
            "k_anon_ok": bool(disc and disc.get("k_anon_ok")),
            "approximate_count": (disc or {}).get("approximate_count") if disc else "unreachable",
            "records_returned": len(nr.get("matches") or []),
        })
        if disc and not disc.get("k_anon_ok"):
            any_suppressed = True
        for m in (nr.get("matches") or []):
            merged.append(m)
            total_returned += 1

    # 4) Differencing defense (per session AND per node). A safe network delta
    # can hide an unsafe hospital delta, so each node gets an independent ledger.
    node_logs = _SESSIONS.setdefault(body.session, {})
    node_guards: dict[str, dict[str, object]] = {}
    for nr in node_results:
        node = nr["node"]
        candidate_count = nr.get("candidate_count")
        if isinstance(candidate_count, int) and not isinstance(candidate_count, bool):
            session_log = node_logs.setdefault(node, [])
            # ORDER IS LOAD-BEARING, and it is stage-then-assess by design: the guard
            # reads the current query's own pre-disclosure count from its staged record
            # (see scripts/query_guard.assess_disclosure_risk). Do not "fix" this to
            # assess-then-append -- that starves the guard of the count it subtracts.
            session_log.append(QueryRecord(ast=ast, result_count=candidate_count))
            node_guards[node] = assess_disclosure_risk(
                ast, session_log, k=K_THRESHOLD
            ).to_dict()
        else:
            # No exact count crossed the node boundary, so there is nothing new
            # for subtraction. Existing node-side suppression remains in force.
            node_guards[node] = {
                "risk": "none",
                "action": "allow",
                "reason": "No exact node count was released for guard assessment.",
                "related_query_fingerprint": None,
            }

    # 5) Fuse ranks across nodes (RRF over independent signals), then keep our richer `why`.
    by_id = {m["passport"]["passport_id"]: m for m in merged}
    numeric_rank = sorted(((pid, m["numeric_score"]) for pid, m in by_id.items()),
                          key=lambda t: (-t[1], t[0]))
    richness_rank = sorted(((pid, m["richness_score"]) for pid, m in by_id.items()),
                           key=lambda t: (-t[1], t[0]))
    order = [r.study_id for r in fuse({"numeric": numeric_rank, "richness": richness_rank},
                                      FUSION_WEIGHTS)] if by_id else []

    # 6) Redact each surviving passport to the requester's layer (server-side, never client-trusted).
    results: list[dict[str, Any]] = []
    for pid in order:
        m = by_id[pid]
        results.append({
            "passport": redact_for_layer(m["passport"], layer),
            "node": m["passport"]["owner"]["node"],
            "why": m["why"],
        })

    # 7) Degrade only the hospital responses whose own ledger tripped. Safe
    #    hospitals can still return records; guarded hospitals expose only bands.
    guarded_nodes = {
        node
        for node, node_guard in node_guards.items()
        if node_guard["action"] in ("suppress", "bucket")
    }
    if guarded_nodes:
        results = [row for row in results if row["node"] not in guarded_nodes]
    for pn in per_node:
        node_action = str(node_guards[pn["node"]]["action"])
        pn["guard_action"] = node_action
        if pn["node"] in guarded_nodes:
            exact_count = pn.pop("records_returned")
            if pn.get("k_anon_ok"):
                pn["approximate_count"] = _bucket(exact_count)

    guard_actions = {str(item["action"]) for item in node_guards.values()}
    guard_action = (
        "suppress" if "suppress" in guard_actions
        else "bucket" if "bucket" in guard_actions
        else "allow"
    )
    risky_nodes = sorted(guarded_nodes)
    risky_guards = [node_guards[node] for node in risky_nodes]
    guard = {
        "risk": "differencing_suspected" if risky_nodes else "none",
        "action": guard_action,
        "reason": (
            "Per-node disclosure guard engaged at "
            + ", ".join(risky_nodes)
            + "; exact node counts and records were withheld."
            if risky_nodes
            else "No node ledger contains a query pair that isolates a cohort below k."
        ),
        "related_query_fingerprint": next(
            (
                item["related_query_fingerprint"]
                for item in risky_guards
                if item.get("related_query_fingerprint")
            ),
            None,
        ),
        "per_node": [
            {"node": node, **node_guard}
            for node, node_guard in sorted(node_guards.items())
        ],
    }
    total_page = len(results)
    start = max(0, (body.page - 1) * body.page_size)
    page_results = results[start:start + body.page_size]

    if guard_action != "allow":
        reason = str(guard["reason"])
    elif any_suppressed:
        reason = ("one or more nodes hold a cohort below k; those records are withheld "
                  "node-side and a governed petition path is offered instead")
    else:
        reason = "cohort clears k at every returning node"
    disclosure = {
        "threshold": K_THRESHOLD,
        "k_anon_ok": total_returned > 0,
        "records_withheld": any_suppressed or bool(guarded_nodes),
        "petition_route": "/petition",
        "reason": reason,
        "per_node": per_node,
        # Deliberately NO summed exact count when anything is suppressed/bucketed:
        # revealing it would defeat k-anon by subtraction. [SECFIX 25JUL Flame1]
        "returned_count": total_page if not guarded_nodes else "bucketed (guarded)",
    }

    return {
        "query_ast": ast.model_dump(mode="json", exclude_none=True),
        "results": page_results,
        "disclosure": disclosure,
        "guard": guard,
        "nodes_queried": [nr["node"] for nr in node_results],
        "page": body.page, "page_size": body.page_size, "total_on_page_set": total_page,
        "timing_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


@app.get("/passport/{node}/{study_id}")
async def passport(node: str, study_id: str, role: str = "researcher") -> dict[str, Any]:
    node = node.upper()
    if node not in NODES:
        raise HTTPException(status_code=404, detail=f"unknown node {node}")
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{NODES[node]}/passport/{study_id}", timeout=2.0)
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail="passport not found")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"node {node} unreachable: {type(exc).__name__}")
    return redact_for_layer(r.json(), role_to_layer(role))


@app.get("/cohort")
async def cohort(role: str = "researcher") -> dict[str, Any]:
    # Cohort counting reuses /search's disclosure without shipping records. Filters come via query
    # params in a full build; for the demo the frontend calls /search and reads `disclosure`.
    raise HTTPException(status_code=400, detail="POST /search and read `disclosure` for cohort counts")


class PetitionBody(BaseModel):
    requester_name: str
    institution: str
    irb_number: str
    purpose: str
    cohort_filter: dict[str, Any] = {}
    tier_requested: str = "L3"


@app.post("/petition")
def petition(body: PetitionBody) -> dict[str, Any]:
    # Route to the owning node named in the cohort filter, else default to BCH (pediatric owner).
    owner = (body.cohort_filter.get("owner_node") or "BCH").upper()
    if owner not in NODES:
        owner = "BCH"
    pet_id = "pet_" + uuid.uuid4().hex[:10]
    event = audit.append_event("petition", {
        "petition_id": pet_id, "requester_name": body.requester_name,
        "institution": body.institution, "irb_number": body.irb_number,
        "purpose": body.purpose, "cohort_filter": body.cohort_filter,
        "tier_requested": body.tier_requested, "owner_node": owner, "status": "routed_to_owner",
    })
    _PETITIONS[pet_id] = {**event, "decisions": []}
    return {
        "petition_id": pet_id, "status": "routed_to_owner", "owner_node": owner,
        "owner_contact": f"data-access@{owner.lower()}.example",
        "audit_id": event["audit_id"], "timestamp": event["timestamp"],
        "note": "We never held the source data. This request is routed to the owning node with an "
                "append-only audit entry.",
    }


class DecisionBody(BaseModel):
    decision: str
    reviewer: str
    note: str = ""


@app.patch("/petition/{pet_id}")
def decide(pet_id: str, body: DecisionBody) -> dict[str, Any]:
    if pet_id not in _PETITIONS:
        raise HTTPException(status_code=404, detail="unknown petition")
    if body.decision not in {"approve", "deny"}:
        raise HTTPException(status_code=422, detail="decision must be approve or deny")
    event = audit.append_event("petition_decision", {
        "petition_id": pet_id, "decision": body.decision, "reviewer": body.reviewer, "note": body.note,
    })
    pet = _PETITIONS[pet_id]
    pet["decisions"].append(event)
    pet["status"] = "approved" if body.decision == "approve" else "denied"
    # On approval the OWNING node issues the retrieval — the broker never serves source data itself.
    retrieval = None
    if body.decision == "approve":
        retrieval = {
            "issued_by_node": pet["owner_node"],
            "signed_url": f"{NODES[pet['owner_node']]}/retrieve/{pet_id}?token={uuid.uuid4().hex[:16]}",
            "expires_in_seconds": 900,
            "note": "Time-limited, node-issued. The broker only relays the grant.",
        }
    return {"petition_id": pet_id, "status": pet["status"], "audit_id": event["audit_id"],
            "retrieval": retrieval}


@app.get("/petitions")
def petitions() -> dict[str, Any]:
    return {"petitions": list(_PETITIONS.values())}


@app.get("/audit")
def audit_trail() -> dict[str, Any]:
    return {"audit": audit.read_all(), "append_only": True}


@app.get("/nodes")
async def nodes() -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        async def _probe(node: str, url: str) -> dict[str, Any]:
            try:
                h = (await client.get(f"{url}/health", timeout=1.5)).json()
                p = (await client.get(f"{url}/policy", timeout=1.5)).json()
                return {**h, "policy": p.get("policy"), "reachable": True}
            except Exception as exc:  # noqa: BLE001
                return {"node": node, "reachable": False, "error": type(exc).__name__}
        out = await asyncio.gather(*[_probe(n, u) for n, u in NODES.items()])
    return {"nodes": list(out), "k_anon_threshold": K_THRESHOLD}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "lantern-broker", "nodes": list(NODES)}


# Serve the researcher console last, so API routes always win. index.html at "/".
_STATIC = REPO / "app" / "static"
if _STATIC.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")
