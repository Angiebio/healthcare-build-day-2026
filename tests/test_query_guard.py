"""Executable differencing attacks against the per-session query guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.measure_extract import extract_measurements
from scripts.query_ast import GOLDEN_QUERY, compile_query
from scripts.query_guard import QueryRecord, assess_disclosure_risk, fingerprint


NODE_DATA = Path(r"C:\Users\ajohn\hackdata\provider-node\data")


def _age_query(maximum: float):
    return compile_query(
        None,
        {
            "population": {"age_max_years": maximum},
            "imaging": {"modality": ["MR"], "body_site": ["BRAIN"]},
            "access": {"min_layer": "L1"},
        },
    )


def test_fingerprint_is_stable_when_filter_order_changes() -> None:
    first = compile_query(
        None,
        {
            "imaging": {"modality": ["MR", "CT"], "body_site": ["BRAIN"]},
            "clinical": {"concepts": ["SNOMED:12738006", "HPO:0002119"]},
        },
    )
    second = compile_query(
        None,
        {
            "clinical": {"concepts": ["HPO:0002119", "SNOMED:12738006"]},
            "imaging": {"body_site": ["BRAIN"], "modality": ["CT", "MR"]},
        },
    )
    assert fingerprint(first) == fingerprint(second)


def test_actual_two_query_attack_is_bucketed() -> None:
    passports = [{"age": age} for age in range(11)]
    broad = _age_query(10.0)
    narrow = _age_query(9.0)

    broad_count = sum(item["age"] <= 10.0 for item in passports)
    narrow_count = sum(item["age"] <= 9.0 for item in passports)
    assert broad_count - narrow_count == 1

    log = [
        QueryRecord(ast=broad, result_count=broad_count),
        QueryRecord(ast=narrow, result_count=narrow_count),
    ]
    verdict = assess_disclosure_risk(narrow, log, k=10)

    assert verdict.risk == "differencing_suspected"
    assert verdict.action == "bucket"
    assert "fewer than k=10 records" in verdict.reason
    assert "isolates 1 record" not in verdict.reason
    assert verdict.related_query_fingerprint == fingerprint(broad)


def test_large_delta_is_allowed() -> None:
    broad = _age_query(10.0)
    narrow = _age_query(9.0)
    verdict = assess_disclosure_risk(
        narrow,
        [
            QueryRecord(ast=broad, result_count=50),
            QueryRecord(ast=narrow, result_count=30),
        ],
        k=10,
    )
    assert verdict.risk == "none"
    assert verdict.action == "allow"


def test_related_query_without_current_count_buckets_conservatively() -> None:
    broad = _age_query(10.0)
    narrow = _age_query(9.0)
    verdict = assess_disclosure_risk(
        narrow, [QueryRecord(ast=broad, result_count=11)], k=10
    )
    assert verdict.risk == "differencing_suspected"
    assert verdict.action == "bucket"


def test_malformed_internal_state_suppresses() -> None:
    verdict = assess_disclosure_risk(_age_query(9.0), [object()], k=10)  # type: ignore[list-item]
    assert verdict.risk == "differencing_suspected"
    assert verdict.action == "suppress"
    assert "failed closed" in verdict.reason


@pytest.mark.skipif(not NODE_DATA.exists(), reason="locked challenge corpus unavailable")
def test_locked_ladder_real_exploit_pair_is_bucketed() -> None:
    """Verified BCH pair: >12 mm (48) versus GA ≤31 weeks (39) isolates nine."""

    broad_filters = GOLDEN_QUERY.model_dump(mode="json", exclude_none=True)
    broad_filters["numeric"][0]["value"] = 12.0
    broad = compile_query(None, broad_filters)
    narrow_filters = broad.model_dump(mode="json", exclude_none=True)
    narrow_filters["population"]["gestational_age_max_weeks"] = 31.0
    narrow = compile_query(None, narrow_filters)

    broad_count = 0
    narrow_count = 0
    rows = json.loads((NODE_DATA / "bch_data.json").read_text(encoding="utf-8"))
    for row in rows:
        if row["BodyPartExamined"] != "FETAL":
            continue
        measurements = extract_measurements(row["Diagnosis"])
        widths = [
            measurement.value
            for measurement in measurements
            if measurement.quantity == "lateral_ventricular_atrial_width"
        ]
        if not any(value > 12.0 for value in widths):
            continue
        broad_count += 1
        gestational_ages = [
            measurement.value
            for measurement in measurements
            if measurement.quantity == "gestational_age_weeks"
        ]
        if gestational_ages and gestational_ages[0] <= 31.0:
            narrow_count += 1

    assert (broad_count, narrow_count, broad_count - narrow_count) == (48, 39, 9)
    verdict = assess_disclosure_risk(
        narrow,
        [
            QueryRecord(ast=broad, result_count=broad_count),
            QueryRecord(ast=narrow, result_count=narrow_count),
        ],
        k=10,
    )
    assert verdict.risk == "differencing_suspected"
    assert verdict.action == "bucket"
    assert "fewer than k=10 records" in verdict.reason
    assert "isolates 9 record" not in verdict.reason
