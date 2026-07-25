"""Tests for honest passport capability reporting."""

from __future__ import annotations

import pytest

from scripts.computational_readiness import computational_readiness
from scripts.measure_extract import extract_measurements


def test_measurements_enable_only_grounded_affordances() -> None:
    measurements = extract_measurements(
        "At 24 weeks gestation, the atrial width measures 12.4 mm."
    )
    readiness = computational_readiness({"measurements": measurements})

    assert readiness == {
        "has_quantitative_measurements": True,
        "measurement_count": 2,
        "quantities_available": [
            "gestational_age_weeks",
            "lateral_ventricular_atrial_width",
        ],
        "supports_quantitative_cohort_analysis": True,
        "supports_threshold_stratification": True,
        "missing_for_full_computability": [
            "voxel_geometry",
            "acquisition_parameters",
            "pixel_data",
        ],
    }


def test_empty_passport_claims_no_quantitative_capability() -> None:
    readiness = computational_readiness({})
    assert readiness["has_quantitative_measurements"] is False
    assert readiness["measurement_count"] == 0
    assert readiness["supports_quantitative_cohort_analysis"] is False
    assert readiness["supports_threshold_stratification"] is False
    assert readiness["quantities_available"] == []


def test_present_fields_are_removed_from_missing_list() -> None:
    readiness = computational_readiness(
        {
            "measurements": [],
            "voxel_geometry": {"spacing": [1.0, 1.0, 1.0]},
            "acquisition_parameters": {"sequence": "T2"},
            "pixel_data_available": True,
        }
    )
    assert readiness["missing_for_full_computability"] == []


def test_unknown_measurement_quantity_fails_loud() -> None:
    with pytest.raises(ValueError, match="unknown quantity"):
        computational_readiness(
            {
                "measurements": [
                    {"quantity": "magic_radiomics", "value": 1.0, "unit": "score"}
                ]
            }
        )
