"""Tests for the cohort fitness funnel and deterministic MMR."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.cohort_shape import cohort_funnel, count_bucket, diversify
from scripts.kanon import apply_disclosure
from scripts.query_ast import GOLDEN_QUERY


FIXTURES = Path(__file__).parents[1] / "app" / "static" / "fixtures.json"


def _passport(
    passport_id: str,
    *,
    width: float | None,
    node: str = "BCH",
    age: float = 6.0,
    age_band: str = "5-9",
    sex: str = "F",
    body_part: str = "FETAL",
    score: float = 1.0,
    disclosure_ok: bool = True,
    access_layer: str = "L1",
):
    measurements = (
        [
            {
                "quantity": "lateral_ventricular_atrial_width",
                "value": width,
                "unit": "mm",
            }
        ]
        if width is not None
        else []
    )
    return {
        "passport_id": passport_id,
        "node": node,
        "age_years": age,
        "age_band": age_band,
        "stage": "school_age",
        "sex": sex,
        "population": {
            "basis": "gestational",
            "gestational_age_weeks": 24.0,
            "pediatric_stage": "fetal",
            "public_age_band": "fetal",
            "sex": sex,
        },
        "modality": "MR",
        "body_part": body_part,
        "concepts": ["SNOMED:276654001", "HPO:0002119"],
        "measurements": measurements,
        "score": score,
        "disclosure_ok": disclosure_ok,
        "access_layer": access_layer,
    }


def test_funnel_computes_five_monotonic_counts() -> None:
    candidates = [
        _passport("p1", width=12.4),
        _passport("p2", width=9.0),
        _passport("p3", width=None),
        _passport("p4", width=14.0, body_part="HEART"),
        _passport("p5", width=13.0, disclosure_ok=False),
        _passport("p6", width=11.0, access_layer="L2"),
    ]
    disclosure = apply_disclosure(
        [{"study_id": str(index)} for index in range(10)], threshold=10
    )
    funnel = cohort_funnel(candidates, GOLDEN_QUERY, disclosure)

    assert [stage["count"] for stage in funnel.values()] == [5, 4, 3, 2, 1]
    assert [stage["label"] for stage in funnel.values()] == [
        "Clinically relevant",
        "With extractable measurements",
        "Meeting the numeric constraint",
        "Passing disclosure policy",
        "Accessible at your current authorization",
    ]


@pytest.mark.skipif(not FIXTURES.exists(), reason="compiled demo fixtures unavailable")
def test_golden_query_returns_locked_225_studies_from_demo_fixtures() -> None:
    passports = json.loads(FIXTURES.read_text(encoding="utf-8"))["passports"]
    disclosure = apply_disclosure(
        [{"study_id": str(index)} for index in range(225)], threshold=10
    )
    funnel = cohort_funnel(passports, GOLDEN_QUERY, disclosure)
    assert funnel["meeting_numeric_constraint"]["count"] == 225


@pytest.mark.parametrize(
    ("count", "bucket"),
    [
        (0, "<10"),
        (9, "<10"),
        (10, "<10"),
        (11, "11-25"),
        (25, "11-25"),
        (26, "26-50"),
        (51, "51-100"),
        (101, "100+"),
    ],
)
def test_count_bucket_boundaries(count: int, bucket: str) -> None:
    assert count_bucket(count) == bucket


def test_diversify_prefers_a_different_site_and_is_deterministic() -> None:
    results = [
        _passport("a", width=12.0, node="BCH", sex="F", score=1.0),
        _passport("b", width=13.0, node="BCH", sex="F", score=0.99),
        _passport(
            "c",
            width=14.0,
            node="MGH",
            age=15.0,
            age_band="15-17",
            sex="M",
            body_part="HEART",
            score=0.95,
        ),
    ]
    first = diversify(results, k=2, lambda_=0.7)
    second = diversify(list(reversed(results)), k=2, lambda_=0.7)

    assert [item["passport_id"] for item in first] == ["a", "c"]
    assert [item["passport_id"] for item in first] == [
        item["passport_id"] for item in second
    ]


def test_diversify_ties_break_by_passport_id() -> None:
    results = [
        _passport("z", width=12.0),
        _passport("a", width=12.0),
    ]
    assert [item["passport_id"] for item in diversify(results, k=2)] == ["a", "z"]


def test_invalid_diversity_parameters_fail_loud() -> None:
    with pytest.raises(ValueError, match="lambda"):
        diversify([_passport("a", width=12.0)], k=1, lambda_=1.5)
    with pytest.raises(ValueError, match="duplicate"):
        diversify(
            [_passport("a", width=12.0), _passport("a", width=13.0)], k=2
        )
