"""Cohort fitness funnel and deterministic diversity optimization."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .kanon import Disclosure
from .query_ast import NumericConstraint, QueryAST


_LAYER_ORDER = {"L0": 0, "L1": 1, "L2": 2}


def count_bucket(n: int) -> str:
    """Return a privacy-oriented display bucket.

    The supplied display vocabulary has no exact bucket for 10, so the threshold
    boundary is conservatively grouped with the suppressed ``<10`` label rather
    than promoted into a factually narrower released range.
    """

    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("count must be a non-negative integer")
    if n <= 10:
        return "<10"
    if n <= 25:
        return "11-25"
    if n <= 50:
        return "26-50"
    if n <= 100:
        return "51-100"
    return "100+"


def cohort_funnel(
    candidates: list[Mapping[str, Any]],
    ast: QueryAST,
    disclosure: Disclosure | Mapping[str, Any],
) -> dict[str, dict[str, object]]:
    """Compute the five-stage cohort fitness funnel from passport facts.

    Every stage is a subset of the previous stage. Counts are accompanied by a
    display bucket so callers can honor count-disclosure policy without
    recomputing cohort logic in the UI.
    """

    if not isinstance(candidates, list):
        raise TypeError("candidates must be a list")
    if any(not isinstance(candidate, Mapping) for candidate in candidates):
        raise TypeError("every candidate must be a passport mapping")
    if not isinstance(ast, QueryAST):
        raise TypeError("ast must be a validated QueryAST")

    clinically_relevant = [
        passport for passport in candidates if _matches_clinical_filters(passport, ast)
    ]
    measurable = [
        passport
        for passport in clinically_relevant
        if bool(_measurements(passport))
    ]
    numeric_match = [
        passport
        for passport in measurable
        if _matches_numeric_constraints(passport, ast.numeric)
    ]

    disclosure_ok = _disclosure_ok(disclosure)
    disclosed = (
        [
            passport
            for passport in numeric_match
            if passport.get("disclosure_ok", True) is True
        ]
        if disclosure_ok
        else []
    )
    accessible = [
        passport for passport in disclosed if _is_accessible(passport, ast.access.min_layer)
    ]

    return {
        "clinically_relevant": _funnel_stage(
            "Clinically relevant", len(clinically_relevant)
        ),
        "with_extractable_measurements": _funnel_stage(
            "With extractable measurements", len(measurable)
        ),
        "meeting_numeric_constraint": _funnel_stage(
            "Meeting the numeric constraint", len(numeric_match)
        ),
        "passing_disclosure_policy": _funnel_stage(
            "Passing disclosure policy", len(disclosed)
        ),
        "accessible_at_current_authorization": _funnel_stage(
            "Accessible at your current authorization", len(accessible)
        ),
    }


def diversify(
    results: list[Mapping[str, Any]],
    k: int,
    lambda_: float = 0.7,
) -> list[Mapping[str, Any]]:
    """Select a deterministic MMR cohort over five corpus-grounded axes.

    Relevance is read from ``score`` (default 1.0). Redundancy is mean similarity
    over node, age band, sex, body part, and measurement-quantity profile.
    Identical MMR values are resolved by stable ``passport_id`` order.
    """

    if not isinstance(results, list):
        raise TypeError("results must be a list")
    if any(not isinstance(result, Mapping) for result in results):
        raise TypeError("every result must be a passport mapping")
    if isinstance(k, bool) or not isinstance(k, int) or k < 0:
        raise ValueError("k must be a non-negative integer")
    if (
        isinstance(lambda_, bool)
        or not isinstance(lambda_, (int, float))
        or not math.isfinite(float(lambda_))
        or not 0.0 <= float(lambda_) <= 1.0
    ):
        raise ValueError("lambda_ must be finite and between 0 and 1")
    if k == 0 or not results:
        return []

    by_id: dict[str, Mapping[str, Any]] = {}
    raw_scores: dict[str, float] = {}
    for result in results:
        passport_id = result.get("passport_id")
        if not isinstance(passport_id, str) or not passport_id:
            raise ValueError("every result requires a non-empty passport_id")
        if passport_id in by_id:
            raise ValueError(f"duplicate passport_id {passport_id!r}")
        score = result.get("score", 1.0)
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
        ):
            raise ValueError(f"passport {passport_id!r} has a non-finite score")
        by_id[passport_id] = result
        raw_scores[passport_id] = float(score)

    relevance = _normalize_scores(raw_scores)
    remaining = sorted(by_id)
    selected_ids: list[str] = []

    while remaining and len(selected_ids) < min(k, len(results)):
        ranked_candidates: list[tuple[float, str]] = []
        for passport_id in remaining:
            redundancy = (
                max(
                    _passport_similarity(
                        by_id[passport_id], by_id[selected_id]
                    )
                    for selected_id in selected_ids
                )
                if selected_ids
                else 0.0
            )
            mmr = float(lambda_) * relevance[passport_id] - (
                1.0 - float(lambda_)
            ) * redundancy
            ranked_candidates.append((mmr, passport_id))

        ranked_candidates.sort(key=lambda item: (-round(item[0], 15), item[1]))
        chosen = ranked_candidates[0][1]
        selected_ids.append(chosen)
        remaining.remove(chosen)

    return [by_id[passport_id] for passport_id in selected_ids]


def _funnel_stage(label: str, count: int) -> dict[str, object]:
    return {"label": label, "count": count, "bucket": count_bucket(count)}


def _matches_clinical_filters(
    passport: Mapping[str, Any], ast: QueryAST
) -> bool:
    population = ast.population
    passport_basis = _population_value(
        passport, "basis", fallback_key="population_basis", default="chronological"
    )
    if passport_basis != population.basis:
        return False

    passport_sex = _population_value(passport, "sex", fallback_key="sex")
    if population.sex is not None and passport_sex != population.sex:
        return False

    if population.basis == "gestational":
        if (
            population.gestational_age_min_weeks is not None
            or population.gestational_age_max_weeks is not None
        ):
            gestational_age = _population_value(
                passport,
                "gestational_age_weeks",
                fallback_key="gestational_age_weeks",
            )
            if not _is_finite_number(gestational_age):
                return False
            if (
                population.gestational_age_min_weeks is not None
                and gestational_age < population.gestational_age_min_weeks
            ):
                return False
            if (
                population.gestational_age_max_weeks is not None
                and gestational_age > population.gestational_age_max_weeks
            ):
                return False
    else:
        stage = _population_value(
            passport, "pediatric_stage", fallback_key="stage"
        )
        if population.stages and stage not in population.stages:
            return False
        if population.age_min_years is not None or population.age_max_years is not None:
            age = _population_value(passport, "age_years", fallback_key="age_years")
            if not _is_finite_number(age):
                return False
            if population.age_min_years is not None and age < population.age_min_years:
                return False
            if population.age_max_years is not None and age > population.age_max_years:
                return False

    modality = _imaging_value(passport, "modality", fallback_key="modality")
    if ast.imaging.modality and modality not in ast.imaging.modality:
        return False
    body_part = _imaging_value(
        passport, "body_part_raw", fallback_key="body_part"
    )
    if body_part is None:
        body_part = passport.get("body_site")
    if ast.imaging.body_site and body_part not in ast.imaging.body_site:
        return False

    available_concepts = passport.get("concepts", [])
    if not isinstance(available_concepts, (list, tuple, set)):
        raise TypeError("passport concepts must be a sequence")
    if not set(ast.clinical.concepts).issubset(set(available_concepts)):
        return False

    summary = passport.get("clean_summary", passport.get("summary", ""))
    if ast.clinical.text_terms:
        if not isinstance(summary, str):
            raise TypeError("passport clean summary must be a string")
        lowered = summary.lower()
        if any(term.lower() not in lowered for term in ast.clinical.text_terms):
            return False
    return True


def _population_value(
    passport: Mapping[str, Any],
    field: str,
    *,
    fallback_key: str,
    default: object = None,
) -> object:
    population = passport.get("population")
    if population is not None:
        if not isinstance(population, Mapping):
            raise TypeError("passport population must be a mapping")
        if field in population:
            return population[field]
    return passport.get(fallback_key, default)


def _imaging_value(
    passport: Mapping[str, Any],
    field: str,
    *,
    fallback_key: str,
) -> object:
    imaging = passport.get("imaging")
    if imaging is not None:
        if not isinstance(imaging, Mapping):
            raise TypeError("passport imaging must be a mapping")
        if field in imaging:
            return imaging[field]
    return passport.get(fallback_key)


def _matches_numeric_constraints(
    passport: Mapping[str, Any], constraints: list[NumericConstraint]
) -> bool:
    if not constraints:
        return True
    measurements = _measurements(passport)
    return all(
        any(_measurement_satisfies(measurement, constraint) for measurement in measurements)
        for constraint in constraints
    )


def _measurement_satisfies(
    measurement: object, constraint: NumericConstraint
) -> bool:
    quantity = _measurement_field(measurement, "quantity")
    unit = _measurement_field(measurement, "unit")
    value = _measurement_field(measurement, "value")
    if quantity != constraint.quantity or unit != constraint.unit:
        return False
    if not _is_finite_number(value):
        raise ValueError("measurement value must be finite")
    if constraint.op == "lt":
        return value < constraint.value
    if constraint.op == "lte":
        return value <= constraint.value
    if constraint.op == "gt":
        return value > constraint.value
    if constraint.op == "gte":
        return value >= constraint.value
    if constraint.op == "between":
        if constraint.range is None:
            raise ValueError("validated between constraint unexpectedly lacks a range")
        return constraint.range[0] <= value <= constraint.range[1]
    raise ValueError(f"unsupported validated numeric operator {constraint.op!r}")


def _measurements(passport: Mapping[str, Any]) -> list[object]:
    measurements = passport.get("measurements", [])
    if not isinstance(measurements, list):
        raise TypeError("passport measurements must be a list")
    return measurements


def _measurement_field(measurement: object, field: str) -> Any:
    if isinstance(measurement, Mapping):
        return measurement.get(field)
    if hasattr(measurement, field):
        return getattr(measurement, field)
    raise TypeError("measurement must be a mapping or typed measurement object")


def _disclosure_ok(disclosure: Disclosure | Mapping[str, Any]) -> bool:
    if isinstance(disclosure, Disclosure):
        return disclosure.k_anon_ok
    if isinstance(disclosure, Mapping):
        value = disclosure.get("k_anon_ok")
        if not isinstance(value, bool):
            raise ValueError("disclosure mapping requires boolean k_anon_ok")
        return value
    raise TypeError("disclosure must be a Disclosure or mapping")


def _is_accessible(passport: Mapping[str, Any], current_layer: str) -> bool:
    if "accessible" in passport:
        accessible = passport["accessible"]
        if not isinstance(accessible, bool):
            raise TypeError("passport accessible flag must be boolean")
        return accessible
    required_layer = passport.get("access_layer", "L1")
    if required_layer not in _LAYER_ORDER:
        raise ValueError(f"unknown passport access layer {required_layer!r}")
    return _LAYER_ORDER[required_layer] <= _LAYER_ORDER[current_layer]


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if all(0.0 <= score <= 1.0 for score in scores.values()):
        return dict(scores)
    minimum = min(scores.values())
    maximum = max(scores.values())
    if maximum == minimum:
        return {passport_id: 1.0 for passport_id in scores}
    return {
        passport_id: (score - minimum) / (maximum - minimum)
        for passport_id, score in scores.items()
    }


def _passport_similarity(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> float:
    categorical = [
        ("node", "institution"),
        ("age_band",),
        ("sex",),
        ("body_part", "body_site"),
    ]
    matches = [
        float(_first_present(first, keys) == _first_present(second, keys))
        for keys in categorical
    ]
    matches.append(
        _jaccard(_measurement_profile(first), _measurement_profile(second))
    )
    return sum(matches) / len(matches)


def _first_present(passport: Mapping[str, Any], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in passport:
            return passport[key]
    return "<missing>"


def _measurement_profile(passport: Mapping[str, Any]) -> frozenset[str]:
    explicit = passport.get("measurement_profile")
    if explicit is not None:
        if not isinstance(explicit, (list, tuple, set, frozenset)):
            raise TypeError("measurement_profile must be a sequence")
        return frozenset(str(item) for item in explicit)
    return frozenset(
        str(_measurement_field(measurement, "quantity"))
        for measurement in _measurements(passport)
    )


def _jaccard(first: frozenset[str], second: frozenset[str]) -> float:
    if not first and not second:
        return 1.0
    return len(first & second) / len(first | second)


def _is_finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )
