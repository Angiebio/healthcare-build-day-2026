"""Boundary tests for privacy-preserving age generalization."""

from __future__ import annotations

import math

import pytest

from scripts.age_band import pediatric_stage, public_age_band, to_age_years


def test_real_age_examples() -> None:
    assert to_age_years("005D") == pytest.approx(5 / 365.25)
    assert to_age_years("018Y") == 18.0
    assert to_age_years("035Y") == 35.0
    assert to_age_years("006M") == 0.5


@pytest.mark.parametrize(
    ("age", "stage"),
    [
        (0.0, "neonate"),
        ((28 / 365.25) - 1e-9, "neonate"),
        (28 / 365.25, "infant"),
        (1.0, "early_childhood"),
        (5.0, "school_age"),
        (12.0, "adolescent"),
        (18.0, "adult"),
        (35.0, "adult"),
    ],
)
def test_stage_boundaries_are_non_overlapping(age: float, stage: str) -> None:
    assert pediatric_stage(age) == stage


@pytest.mark.parametrize(
    ("age", "band"),
    [
        (0.0, "0-1"),
        (1.0, "1-4"),
        (5.0, "5-9"),
        (10.0, "10-14"),
        (15.0, "15-17"),
        (18.0, "18+"),
        (35.0, "18+"),
    ],
)
def test_public_band_boundaries(age: float, band: str) -> None:
    assert public_age_band(age) == band


@pytest.mark.parametrize("bad", ["5D", "000W", "18Y", "", None])
def test_bad_dicom_ages_fail_loud(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        to_age_years(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-1.0, math.inf, math.nan, True])
def test_invalid_numeric_ages_fail_loud(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        pediatric_stage(bad)  # type: ignore[arg-type]
