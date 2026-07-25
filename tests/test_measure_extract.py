"""Tests for the node-side quantitative report compiler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.measure_extract import QUANTITY_VOCABULARY, extract_measurements


NODE_DATA = Path(r"C:\Users\ajohn\hackdata\provider-node\data")


def test_dimension_pair_yields_two_normalized_facts() -> None:
    report = "A right cerebellar mass measures 3.5 x 2.8 cm."
    measurements = extract_measurements(report)

    assert [measurement.value for measurement in measurements] == [35.0, 28.0]
    assert {measurement.unit for measurement in measurements} == {"mm"}
    assert [measurement.raw_value for measurement in measurements] == [3.5, 2.8]
    assert {measurement.raw_unit for measurement in measurements} == {"cm"}
    assert {measurement.quantity for measurement in measurements} == {"lesion_dimension"}
    assert {measurement.laterality for measurement in measurements} == {"right"}


def test_explicit_ef_and_respectively_laterality() -> None:
    report = (
        "Left and right atrial widths are 5.8 mm and 5.5 mm, respectively. "
        "LVEF is calculated at 64% and RVEF is 60%."
    )
    measurements = extract_measurements(report)

    atrial = [
        measurement
        for measurement in measurements
        if measurement.quantity == "lateral_ventricular_atrial_width"
    ]
    assert [(measurement.value, measurement.laterality) for measurement in atrial] == [
        (5.8, "left"),
        (5.5, "right"),
    ]
    assert any(
        measurement.quantity == "left_ventricular_ejection_fraction"
        and measurement.value == 64.0
        and measurement.confidence == 0.99
        for measurement in measurements
    )
    assert any(
        measurement.quantity == "right_ventricular_ejection_fraction"
        and measurement.value == 60.0
        for measurement in measurements
    )


def test_negated_clause_does_not_emit_positive_measurement() -> None:
    assert extract_measurements("There is no evidence of a 12 mm ventricular lesion.") == []


def test_extraction_is_deterministic_across_repeated_runs() -> None:
    report = "At 31 weeks gestation, bilateral atrial widths measure 12.4 mm."
    runs = [extract_measurements(report) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_every_measurement_is_closed_vocab_and_source_traceable() -> None:
    report = "At 24 weeks gestation, a lesion measures 8 mm and LVEF is 58%."
    measurements = extract_measurements(report)

    assert measurements
    for measurement in measurements:
        assert measurement.quantity in QUANTITY_VOCABULARY
        start, end = measurement.span
        source_span = report[start:end]
        assert str(measurement.raw_value).rstrip("0").rstrip(".") in source_span
        assert 0.0 <= measurement.confidence <= 1.0
        assert measurement.provenance == "report_extraction"


@pytest.mark.skipif(not NODE_DATA.exists(), reason="build-day synthetic node corpus unavailable")
def test_real_corpus_extraction_rate_and_hand_checked_precision() -> None:
    """Run all 2,700 reports; four indexed BCH cases were manually checked 25JUL."""

    node_rows: dict[str, list[dict[str, str]]] = {}
    for path in sorted(NODE_DATA.glob("*_data.json")):
        node_rows[path.stem] = json.loads(path.read_text(encoding="utf-8"))

    all_reports = [
        row["Diagnosis"]
        for rows in node_rows.values()
        for row in rows
    ]
    extracted = [extract_measurements(report) for report in all_reports]
    extraction_rate = sum(bool(items) for items in extracted) / len(extracted)

    assert len(all_reports) >= 50
    assert 0.70 <= extraction_rate <= 0.85

    bch = node_rows["bch_data"]
    hand_checked = {
        1: {
            "gestational_age_weeks",
            "lesion_dimension",
            "lateral_ventricular_atrial_width",
        },
        5: {
            "left_ventricular_ejection_fraction",
            "right_ventricular_ejection_fraction",
            "chamber_volume",
        },
        243: {
            "right_ventricular_ejection_fraction",
            "regurgitant_fraction",
            "chamber_volume",
        },
    }
    for row_index, expected_quantities in hand_checked.items():
        actual = {
            measurement.quantity
            for measurement in extract_measurements(bch[row_index]["Diagnosis"])
        }
        assert expected_quantities <= actual
