"""Honest computational-affordance reporting for a study passport."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .measure_extract import QUANTITY_VOCABULARY


def computational_readiness(passport: Mapping[str, Any]) -> dict[str, object]:
    """Describe only the computation supported by fields present in a passport."""

    if not isinstance(passport, Mapping):
        raise TypeError("passport must be a mapping")
    measurements = passport.get("measurements", [])
    if not isinstance(measurements, list):
        raise TypeError("passport measurements must be a list")

    quantities: set[str] = set()
    threshold_ready = False
    for measurement in measurements:
        quantity = _field(measurement, "quantity")
        value = _field(measurement, "value")
        unit = _field(measurement, "unit")
        if quantity not in QUANTITY_VOCABULARY:
            raise ValueError(f"measurement has unknown quantity {quantity!r}")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError("measurement value must be a finite number")
        if not isinstance(unit, str) or not unit:
            raise ValueError("measurement unit must be a non-empty string")
        quantities.add(quantity)
        threshold_ready = True

    missing: list[str] = []
    if not passport.get("voxel_geometry"):
        missing.append("voxel_geometry")
    if not passport.get("acquisition_parameters"):
        missing.append("acquisition_parameters")
    if not (
        passport.get("pixel_data_available") is True
        or bool(passport.get("pixel_data"))
    ):
        missing.append("pixel_data")

    has_measurements = bool(measurements)
    return {
        "has_quantitative_measurements": has_measurements,
        "measurement_count": len(measurements),
        "quantities_available": sorted(quantities),
        "supports_quantitative_cohort_analysis": has_measurements,
        "supports_threshold_stratification": threshold_ready,
        "missing_for_full_computability": missing,
    }


def _field(measurement: object, name: str) -> Any:
    if isinstance(measurement, Mapping):
        if name not in measurement:
            raise ValueError(f"measurement is missing required field {name!r}")
        return measurement[name]
    if hasattr(measurement, name):
        return getattr(measurement, name)
    raise TypeError("measurement must be a mapping or typed measurement object")
