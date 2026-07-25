"""Regression tests for fetal population semantics in demo fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_fixtures import compile_passport


NODE_DATA = Path(r"C:\Users\ajohn\hackdata\provider-node\data")


@pytest.mark.skipif(not NODE_DATA.exists(), reason="locked challenge corpus unavailable")
def test_fetal_fixture_uses_report_gestation_not_maternal_patient_age() -> None:
    rows = json.loads((NODE_DATA / "mgh_data.json").read_text(encoding="utf-8"))
    record = next(row for row in rows if row["BodyPartExamined"] == "FETAL")
    maternal_age = record["PatientAge"]
    passport = compile_passport("MGH", record)

    assert maternal_age.endswith("Y")
    assert passport["population"]["basis"] == "gestational"
    assert 0.0 < passport["population"]["gestational_age_weeks"] <= 45.0
    assert passport["population"]["pediatric_stage"] == "fetal"
    assert passport["population"]["public_age_band"] == "fetal"
    assert "age_years" not in passport["population"]
    assert "PatientAge" in passport["deid_manifest"]["removed"]
    assert "Diagnosis gestational age→gestational weeks" in (
        passport["deid_manifest"]["generalized"]
    )


@pytest.mark.skipif(not NODE_DATA.exists(), reason="locked challenge corpus unavailable")
def test_nonfetal_fixture_remains_chronological() -> None:
    rows = json.loads((NODE_DATA / "bch_data.json").read_text(encoding="utf-8"))
    record = next(row for row in rows if row["BodyPartExamined"] == "BRAIN")
    passport = compile_passport("BCH", record)

    assert passport["population"]["basis"] == "chronological"
    assert passport["population"]["gestational_age_weeks"] is None
    assert passport["population"]["pediatric_stage"] != "fetal"
