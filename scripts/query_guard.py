"""Per-session defense against differencing attacks on cohort counts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal

from .query_ast import QueryAST


@dataclass(frozen=True, slots=True)
class QueryRecord:
    """A query and its pre-disclosure candidate count.

    The current query should be staged in the session log before assessment. That
    gives the guard both counts needed to detect subtraction attacks without
    placing execution state inside the AST security boundary.
    """

    ast: QueryAST
    result_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.ast, QueryAST):
            raise TypeError("QueryRecord.ast must be a validated QueryAST")
        if (
            isinstance(self.result_count, bool)
            or not isinstance(self.result_count, int)
            or self.result_count < 0
        ):
            raise ValueError("QueryRecord.result_count must be a non-negative integer")

    @property
    def query_fingerprint(self) -> str:
        return fingerprint(self.ast)


@dataclass(frozen=True, slots=True)
class RiskVerdict:
    risk: Literal["none", "differencing_suspected"]
    action: Literal["allow", "bucket", "suppress"]
    reason: str
    related_query_fingerprint: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def fingerprint(ast: QueryAST) -> str:
    """Return a stable SHA-256 fingerprint of canonical query semantics."""

    if not isinstance(ast, QueryAST):
        raise TypeError("ast must be a validated QueryAST")
    canonical = _canonicalize(ast.model_dump(mode="json", exclude_none=True))
    payload = json.dumps(
        canonical,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assess_disclosure_risk(
    ast: QueryAST, session_log: list[QueryRecord], k: int = 10
) -> RiskVerdict:
    """Detect a one-constraint subtraction attack and degrade count precision.

    The current query's pre-disclosure count is read from its staged
    ``QueryRecord``. If a structurally related prior query exists but the current
    count has not been staged, the guard buckets conservatively. Malformed state
    or any internal error suppresses; privacy code has no optimistic error mode.
    """

    try:
        if not isinstance(ast, QueryAST):
            raise TypeError("ast must be a validated QueryAST")
        if not isinstance(session_log, list):
            raise TypeError("session_log must be a list")
        if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
            raise ValueError("k must be a positive integer")
        if any(not isinstance(record, QueryRecord) for record in session_log):
            raise TypeError("session_log contains a malformed QueryRecord")

        current_fingerprint = fingerprint(ast)
        current_records = [
            record
            for record in session_log
            if record.query_fingerprint == current_fingerprint
        ]
        current_count = current_records[-1].result_count if current_records else None
        current_constraints = _semantic_constraints(ast)

        related: list[QueryRecord] = []
        for record in session_log:
            if record.query_fingerprint == current_fingerprint:
                continue
            if _constraint_distance(
                current_constraints, _semantic_constraints(record.ast)
            ) == 1:
                related.append(record)

        if not related:
            return RiskVerdict(
                risk="none",
                action="allow",
                reason="No near-duplicate query in this session can isolate a small cohort.",
                related_query_fingerprint=None,
            )

        related.sort(key=lambda record: record.query_fingerprint)
        if current_count is None:
            return RiskVerdict(
                risk="differencing_suspected",
                action="bucket",
                reason=(
                    "A query differing by one constraint was seen in this session; "
                    "the exact count is bucketed because a safe count delta is unavailable."
                ),
                related_query_fingerprint=related[0].query_fingerprint,
            )

        risky = [
            record
            for record in related
            if abs(record.result_count - current_count) < k
        ]
        if risky:
            risky.sort(
                key=lambda record: (
                    abs(record.result_count - current_count),
                    record.query_fingerprint,
                )
            )
            nearest = risky[0]
            return RiskVerdict(
                risk="differencing_suspected",
                action="bucket",
                reason=(
                    "Exact count withheld: a one-constraint query pair isolates "
                    f"fewer than k={k} records."
                ),
                related_query_fingerprint=nearest.query_fingerprint,
            )

        return RiskVerdict(
            risk="none",
            action="allow",
            reason=(
                f"Related queries exist, but every observed count delta is at least k={k}."
            ),
            related_query_fingerprint=None,
        )
    except Exception:
        return RiskVerdict(
            risk="differencing_suspected",
            action="suppress",
            reason=(
                "Disclosure-risk assessment failed closed; exact and bucketed "
                "results are suppressed pending review."
            ),
            related_query_fingerprint=None,
        )


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _canonicalize(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        normalized = [_canonicalize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    return value


def _semantic_constraints(ast: QueryAST) -> dict[str, object]:
    """Flatten the AST into whole executable constraints, not JSON leaves."""

    constraints: dict[str, object] = {}

    def include(key: str, value: object) -> None:
        if value not in (None, [], (), ""):
            constraints[key] = _canonicalize(value)

    population = ast.population
    include("population.basis", population.basis)
    include("population.stages", population.stages)
    include("population.age_min_years", population.age_min_years)
    include("population.age_max_years", population.age_max_years)
    include(
        "population.gestational_age_min_weeks",
        population.gestational_age_min_weeks,
    )
    include(
        "population.gestational_age_max_weeks",
        population.gestational_age_max_weeks,
    )
    include("population.sex", population.sex)

    include("imaging.modality", ast.imaging.modality)
    include("imaging.body_site", ast.imaging.body_site)
    include("clinical.concepts", ast.clinical.concepts)
    include("clinical.text_terms", ast.clinical.text_terms)
    if ast.clinical.expand_ontology:
        constraints["clinical.expand_ontology"] = True

    numeric_constraints = sorted(
        (
            _canonicalize(constraint.model_dump(mode="json", exclude_none=True))
            for constraint in ast.numeric
        ),
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
    )
    quantity_occurrences: dict[str, int] = {}
    for constraint in numeric_constraints:
        quantity = str(constraint["quantity"])
        occurrence = quantity_occurrences.get(quantity, 0)
        quantity_occurrences[quantity] = occurrence + 1
        constraints[f"numeric.{quantity}.{occurrence}"] = constraint

    constraints["access.min_layer"] = ast.access.min_layer
    return constraints


def _constraint_distance(
    first: dict[str, object], second: dict[str, object]
) -> int:
    keys = set(first) | set(second)
    return sum(first.get(key) != second.get(key) for key in keys)
