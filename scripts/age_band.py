"""Privacy-preserving age conversion and generalization."""

from __future__ import annotations

import math
import re


_DICOM_AGE = re.compile(r"^(?P<value>\d{3})(?P<unit>[YMD])$")
_NEONATE_YEARS = 28.0 / 365.25


def to_age_years(patient_age: str) -> float:
    """Convert a DICOM AS value (NNNY, NNNM, or NNND) to fractional years."""

    if not isinstance(patient_age, str):
        raise TypeError("patient_age must be a DICOM age string")
    match = _DICOM_AGE.fullmatch(patient_age)
    if not match:
        raise ValueError(
            f"invalid DICOM PatientAge {patient_age!r}; expected exactly NNNY, NNNM, or NNND"
        )
    value = int(match.group("value"))
    unit = match.group("unit")
    if unit == "Y":
        return float(value)
    if unit == "M":
        return value / 12.0
    return value / 365.25


def pediatric_stage(age_years: float) -> str:
    """Return a total, non-overlapping clinical-development stage."""

    age = _validated_age(age_years)
    if age < _NEONATE_YEARS:
        return "neonate"
    if age < 1.0:
        return "infant"
    if age < 5.0:
        return "early_childhood"
    if age < 12.0:
        return "school_age"
    if age < 18.0:
        return "adolescent"
    return "adult"


def public_age_band(age_years: float) -> str:
    """Generalize exact age before a passport leaves the hospital boundary."""

    age = _validated_age(age_years)
    if age < 1.0:
        return "0-1"
    if age < 5.0:
        return "1-4"
    if age < 10.0:
        return "5-9"
    if age < 15.0:
        return "10-14"
    if age < 18.0:
        return "15-17"
    return "18+"


def _validated_age(age_years: float) -> float:
    if isinstance(age_years, bool) or not isinstance(age_years, (int, float)):
        raise TypeError("age_years must be a real number")
    age = float(age_years)
    if not math.isfinite(age) or age < 0:
        raise ValueError("age_years must be finite and non-negative")
    return age
