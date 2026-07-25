"""Node-local retrieval: does a compiled passport satisfy a validated QueryAST?

WHY THIS LIVES NODE-SIDE (it is the whole trust-boundary claim):
The broker never sees a raw record. Each node compiles its own studies into
passports and evaluates queries against *its own* passports. Only the passport --
never the prose it was compiled from -- is eligible to cross to the broker. This
module is the predicate that decides "match / no match" and, crucially, *why*, so
the explanation ships with the result and a model guess can never wear a clinical
fact's clothes.

Hard filters (a dropped filter is a privacy failure, not a UX convenience):
imaging modality/body-site, population basis + gestational-week bounds + stage,
and the numeric measurement constraints. Concept coding is not yet in the passport
(terminology lane), so concepts/text are treated as soft signals, never a silent
exclude. Pure functions, no I/O.
"""
from __future__ import annotations

from typing import Any

from scripts.query_ast import NumericConstraint, QueryAST


def _passes_numeric(measurement: dict[str, Any], c: NumericConstraint) -> bool:
    if measurement.get("quantity") != c.quantity:
        return False
    if measurement.get("unit") != c.unit:
        return False
    value = measurement.get("value")
    if not isinstance(value, (int, float)):
        return False
    if c.op == "lt":
        return value < c.value
    if c.op == "lte":
        return value <= c.value
    if c.op == "gt":
        return value > c.value
    if c.op == "gte":
        return value >= c.value
    if c.op == "between" and c.range is not None:
        return c.range[0] <= value <= c.range[1]
    return False


def _op_phrase(c: NumericConstraint) -> str:
    sym = {"lt": "<", "lte": "≤", "gt": ">", "gte": "≥"}
    if c.op == "between" and c.range is not None:
        return f"in [{c.range[0]}, {c.range[1]}] {c.unit}"
    return f"{sym.get(c.op, c.op)} {c.value} {c.unit}"


def evaluate(ast: QueryAST, passport: dict[str, Any]) -> dict[str, Any] | None:
    """Return a match dict (passport + why + scores) or None if the passport fails a hard filter."""
    imaging = passport.get("imaging", {})
    population = passport.get("population", {})
    measurements = passport.get("measurements", []) or []
    signals: list[str] = []

    # --- hard imaging filters ---
    if ast.imaging.modality and imaging.get("modality") not in ast.imaging.modality:
        return None
    if ast.imaging.body_site and imaging.get("body_part_raw") not in ast.imaging.body_site:
        return None
    if ast.imaging.modality or ast.imaging.body_site:
        signals.append("imaging")

    # --- population: basis must agree; bounds apply on the axis that basis names ---
    if ast.population.basis == "gestational":
        if population.get("basis") != "gestational":
            return None
        weeks = population.get("gestational_age_weeks")
        lo, hi = ast.population.gestational_age_min_weeks, ast.population.gestational_age_max_weeks
        if lo is not None or hi is not None:
            if not isinstance(weeks, (int, float)):
                return None
            if lo is not None and weeks < lo:
                return None
            if hi is not None and weeks > hi:
                return None
            signals.append("gestational_age")
    else:
        if ast.population.stages and population.get("pediatric_stage") not in ast.population.stages:
            return None
        if ast.population.stages:
            signals.append("population_stage")
    if ast.population.sex and population.get("sex") != ast.population.sex:
        return None

    # --- numeric measurement constraints (the novel axis) ---
    matched_measurements: list[dict[str, Any]] = []
    for c in ast.numeric:
        hit = next((m for m in measurements if _passes_numeric(m, c)), None)
        if hit is None:
            return None  # a numeric constraint the study cannot satisfy is a hard exclude
        matched_measurements.append({
            "quantity": c.quantity, "constraint": _op_phrase(c),
            "value": hit.get("value"), "unit": hit.get("unit"),
            "laterality": hit.get("laterality"), "confidence": hit.get("confidence"),
            "provenance": hit.get("provenance"), "snippet": hit.get("snippet"),
        })
    if ast.numeric:
        signals.append("numeric_match")

    # --- soft signals (never a silent exclude): measurement richness for tie-break ---
    richness = len(measurements)

    # --- build the human-legible reason (explainability is graded, not decoration) ---
    parts: list[str] = []
    if imaging.get("modality") or imaging.get("body_part_raw"):
        parts.append(f"{imaging.get('modality','?')} {imaging.get('body_part_raw','').title()}".strip())
    if "gestational_age" in signals:
        parts.append(f"gestational age {population.get('gestational_age_weeks')} wk")
    elif "population_stage" in signals:
        parts.append(f"stage {population.get('pediatric_stage')}")
    for mm in matched_measurements:
        lat = f"{mm['laterality']} " if mm.get("laterality") else ""
        parts.append(f"{lat}{mm['quantity'].replace('_',' ')} {mm['value']} {mm['unit']} ({mm['constraint']})")

    # numeric score: rank by the most salient matched value (severity-first is clinically sensible);
    # falls back to richness when the query carries no numeric constraint.
    numeric_score = max((mm["value"] for mm in matched_measurements if isinstance(mm["value"], (int, float))),
                        default=0.0)

    return {
        "passport": passport,
        "why": {
            "signals_fired": signals,
            "reason_text": "matched: " + " · ".join(parts) if parts else "matched",
            "measurements_matched": matched_measurements,
        },
        "numeric_score": float(numeric_score),
        "richness_score": float(richness),
    }


def search(ast: QueryAST, passports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate every passport; return the matches (unranked — the broker fuses across nodes)."""
    out: list[dict[str, Any]] = []
    for p in passports:
        m = evaluate(ast, p)
        if m is not None:
            out.append(m)
    return out
