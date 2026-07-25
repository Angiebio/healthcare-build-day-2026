"""Explainable reciprocal-rank fusion for independent search signals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Final


DEFAULT_RRF_K: Final[int] = 60


@dataclass(frozen=True, slots=True)
class SignalContribution:
    rank: int
    source_score: float
    weight: float
    contribution: float


@dataclass(frozen=True, slots=True)
class Ranked:
    study_id: str
    score: float
    why: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def fuse(
    rankings: dict[str, list[tuple[str, float]]],
    weights: dict[str, float],
    *,
    k: int = DEFAULT_RRF_K,
) -> list[Ranked]:
    """Fuse incomparable ranked signals with weighted Reciprocal Rank Fusion.

    RRF uses only order, not incompatible lexical/cosine/numeric score scales,
    and requires no tuning set during a four-hour build. An absent signal is
    simply absent; the remaining lanes continue to produce deterministic output.
    Contributions are retained verbatim for explanation and audit.
    """

    if not isinstance(rankings, dict) or not isinstance(weights, dict):
        raise TypeError("rankings and weights must be dictionaries")
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")

    totals: dict[str, float] = {}
    explanations: dict[str, dict[str, SignalContribution]] = {}

    for signal in sorted(rankings):
        ranking = rankings[signal]
        if signal not in weights:
            raise ValueError(f"missing fusion weight for signal {signal!r}")
        weight = weights[signal]
        _validate_finite_number(weight, f"weight for {signal}")
        if weight < 0:
            raise ValueError(f"weight for {signal!r} cannot be negative")
        if not isinstance(ranking, list):
            raise TypeError(f"ranking for {signal!r} must be a list")

        seen: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            if not isinstance(item, tuple) or len(item) != 2:
                raise TypeError(f"{signal!r} rank {rank} must be a (study_id, score) tuple")
            study_id, source_score = item
            if not isinstance(study_id, str) or not study_id:
                raise ValueError(f"{signal!r} rank {rank} has an invalid study_id")
            if study_id in seen:
                raise ValueError(f"{signal!r} contains duplicate study_id {study_id!r}")
            seen.add(study_id)
            _validate_finite_number(source_score, f"source score for {study_id}")

            contribution = weight / (k + rank)
            totals[study_id] = totals.get(study_id, 0.0) + contribution
            explanations.setdefault(study_id, {})[signal] = SignalContribution(
                rank=rank,
                source_score=float(source_score),
                weight=float(weight),
                contribution=contribution,
            )

    fused: list[Ranked] = []
    for study_id, score in totals.items():
        fired = explanations[study_id]
        signal_names = sorted(fired)
        reason_names = [name.replace("_", " ").replace("-", " ") for name in signal_names]
        why = {
            "signals": {
                name: asdict(fired[name])
                for name in signal_names
            },
            "reason": "matched: " + " · ".join(reason_names),
        }
        fused.append(Ranked(study_id=study_id, score=score, why=why))

    return sorted(fused, key=lambda result: (-result.score, result.study_id))


def _validate_finite_number(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
