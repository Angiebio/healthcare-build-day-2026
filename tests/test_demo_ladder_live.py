"""Exercise the locked demo ladder through the running HTTP stack.

These tests intentionally do not import broker, retrieval, disclosure, or guard
internals. The demo contract is the wire response a judge sees. Start the stack
with ``python -m app.run_all``; when it is absent, this module skips cleanly.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Iterator
from urllib import error, request

import pytest


BROKER = os.environ.get("LANTERN_BROKER_URL", "http://127.0.0.1:8000").rstrip("/")
NODE_URLS = {
    "BCH": os.environ.get("LANTERN_BCH_URL", "http://127.0.0.1:8011").rstrip("/"),
    "MGH": os.environ.get("LANTERN_MGH_URL", "http://127.0.0.1:8012").rstrip("/"),
    "BWH": os.environ.get("LANTERN_BWH_URL", "http://127.0.0.1:8013").rstrip("/"),
}
LOCKED_COUNTS = {
    "ef_lt_40": {"BCH": 30, "MGH": 53, "BWH": 73},
    "atrial_gt_10": {"BCH": 87, "MGH": 78, "BWH": 60},
}
SEVERE_EXACT_COUNTS = frozenset({7, 6, 3})


def _json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 4.0,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="GET" if body is None else "POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        assert response.status == 200, f"{url} returned HTTP {response.status}"
        decoded = json.loads(response.read().decode("utf-8"))
    assert isinstance(decoded, dict), f"{url} returned a non-object JSON payload"
    return decoded


@pytest.fixture(scope="module", autouse=True)
def live_stack() -> None:
    """Skip only when a service cannot be reached; malformed live services fail."""

    endpoints = {"broker": BROKER, **NODE_URLS}
    health: dict[str, dict[str, Any]] = {}
    for name, base_url in endpoints.items():
        try:
            health[name] = _json_request(f"{base_url}/health", timeout=1.0)
        except (error.URLError, TimeoutError, OSError) as exc:
            pytest.skip(
                "live Lantern stack is not running "
                f"({name} unavailable); start it with: python -m app.run_all"
            )

    for name, payload in health.items():
        assert payload.get("ok") is True, f"{name} health check is not healthy: {payload}"


def _session(beat: str) -> str:
    return f"live-ladder-{beat}-{uuid.uuid4().hex}"


def _search(filters: dict[str, Any], *, session: str) -> dict[str, Any]:
    try:
        return _json_request(
            f"{BROKER}/search",
            payload={
                "filters": filters,
                "role": "researcher",
                "session": session,
                "page_size": 500,
            },
            timeout=8.0,
        )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        pytest.fail(f"live broker returned HTTP {exc.code}: {detail}")
    except (error.URLError, TimeoutError, OSError) as exc:
        pytest.fail(f"live stack disappeared during search: {type(exc).__name__}: {exc}")


def _numeric_filters(
    quantity: str,
    op: str,
    value: float,
    unit: str,
    *,
    body_site: str,
    gestational_max: float | None = None,
) -> dict[str, Any]:
    population: dict[str, Any] = {
        "basis": "gestational" if body_site == "FETAL" else "chronological"
    }
    if gestational_max is not None:
        population["gestational_age_max_weeks"] = gestational_max
    return {
        "population": population,
        "imaging": {"modality": ["MR"], "body_site": [body_site]},
        "numeric": [{"quantity": quantity, "op": op, "value": value, "unit": unit}],
        "access": {"min_layer": "L1"},
    }


def _per_node_counts(payload: dict[str, Any]) -> dict[str, int]:
    rows = payload.get("disclosure", {}).get("per_node")
    assert isinstance(rows, list), f"missing disclosure.per_node: {payload}"
    assert {row.get("node") for row in rows} == set(NODE_URLS)
    assert all(row.get("reachable") is True for row in rows), rows
    assert all(row.get("k_anon_ok") is True for row in rows), rows
    return {row["node"]: row["records_returned"] for row in rows}


def _walk_payload_scalars(value: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    """Yield every wire scalar except nondeterministic request timing."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "timing_ms":
                continue
            child_path = f"{path}.{key}"
            yield from _walk_payload_scalars(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_payload_scalars(child, f"{path}[{index}]")
    else:
        yield path, value


def test_live_beat_1_ejection_fraction_family() -> None:
    """The public EF selector means any EF quantity, not only the generic label."""

    filters = _numeric_filters(
        "ejection_fraction", "lt", 40.0, "%", body_site="HEART"
    )
    payload = _search(filters, session=_session("ef"))

    assert payload["guard"]["action"] == "allow"
    assert _per_node_counts(payload) == LOCKED_COUNTS["ef_lt_40"]


def test_live_beat_2_fetal_atrial_width() -> None:
    filters = _numeric_filters(
        "lateral_ventricular_atrial_width",
        "gt",
        10.0,
        "mm",
        body_site="FETAL",
    )
    payload = _search(filters, session=_session("atrial"))

    assert payload["query_ast"]["population"]["basis"] == "gestational"
    assert payload["guard"]["action"] == "allow"
    assert _per_node_counts(payload) == LOCKED_COUNTS["atrial_gt_10"]


def test_live_beat_3_severe_suppresses_without_exact_count_leak() -> None:
    filters = _numeric_filters(
        "lateral_ventricular_atrial_width",
        "gt",
        15.0,
        "mm",
        body_site="FETAL",
    )
    payload = _search(filters, session=_session("severe"))
    per_node = payload["disclosure"]["per_node"]

    assert payload["results"] == []
    assert payload["disclosure"]["records_withheld"] is True
    assert all(row["k_anon_ok"] is False for row in per_node)
    assert all(row["records_returned"] == 0 for row in per_node)
    assert all(row["approximate_count"] == "<10" for row in per_node)

    leaked = [
        (path, value)
        for path, value in _walk_payload_scalars(payload)
        if value in SEVERE_EXACT_COUNTS or str(value) in {"3", "6", "7"}
    ]
    assert not leaked, f"suppressed exact severe count leaked on the wire: {leaked}"


def test_live_beat_4_verified_differencing_pair_is_bucketed() -> None:
    """BCH >12 mm is 48; adding GA <=31 weeks is 39, isolating nine."""

    session = _session("difference")
    broad = _search(
        _numeric_filters(
            "lateral_ventricular_atrial_width",
            "gt",
            12.0,
            "mm",
            body_site="FETAL",
        ),
        session=session,
    )
    assert broad["guard"]["action"] == "allow"

    narrow = _search(
        _numeric_filters(
            "lateral_ventricular_atrial_width",
            "gt",
            12.0,
            "mm",
            body_site="FETAL",
            gestational_max=31.0,
        ),
        session=session,
    )
    assert narrow["query_ast"]["population"]["gestational_age_max_weeks"] == 31.0
    assert narrow["guard"]["risk"] == "differencing_suspected"
    assert narrow["guard"]["action"] == "bucket"
    assert narrow["results"] == []
    assert narrow["disclosure"]["records_withheld"] is True
    assert all(
        not isinstance(row["approximate_count"], int)
        for row in narrow["disclosure"]["per_node"]
        if row["k_anon_ok"]
    )
