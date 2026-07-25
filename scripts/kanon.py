"""Fail-closed cohort disclosure control."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, TypeAlias


Passport: TypeAlias = Mapping[str, Any]
PETITION_ROUTE = (
    "Submit a governed access petition to the owning hospital node for review."
)


@dataclass(frozen=True, slots=True)
class Disclosure:
    count_suppressed: bool
    approximate_count: str
    k_anon_ok: bool
    threshold: int
    petition_route: str
    layer: str
    records: list[Passport] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def apply_disclosure(
    results: list[Passport], threshold: int = 10, layer: str = "L1"
) -> Disclosure:
    """Release records only when the cohort clears a transparent k threshold.

    This is a fail-closed guard: invalid policy, malformed passports, or an
    internal counting exception all return a suppressed disclosure. The simple
    threshold does *not* prevent differencing attacks, where repeated overlapping
    allowed queries reveal a suppressed cohort by subtraction. Production needs
    query-history controls, minimum-overlap rules, and/or differential privacy;
    this build names that exposure rather than implying k-anonymity solves it.
    """

    try:
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0:
            return _suppressed(threshold=threshold, layer=layer)
        if layer not in {"L0", "L1", "L2"}:
            return _suppressed(threshold=threshold, layer=str(layer))
        if not isinstance(results, list):
            return _suppressed(threshold=threshold, layer=layer)
        count = _count_results(results)
        if any(not isinstance(passport, Mapping) for passport in results):
            return _suppressed(threshold=threshold, layer=layer)
        if count < threshold:
            return _suppressed(threshold=threshold, layer=layer)
        return Disclosure(
            count_suppressed=False,
            approximate_count=str(count),
            k_anon_ok=True,
            threshold=threshold,
            petition_route=PETITION_ROUTE,
            layer=layer,
            records=list(results),
        )
    except Exception:
        # Privacy gates have only one safe error mode: closed.
        return _suppressed(threshold=threshold, layer=str(layer))


def _count_results(results: list[Passport]) -> int:
    """Isolated seam used to prove an internal counting failure stays closed."""

    return len(results)


def _suppressed(*, threshold: object, layer: str) -> Disclosure:
    safe_threshold = threshold if isinstance(threshold, int) and not isinstance(threshold, bool) and threshold > 0 else 10
    return Disclosure(
        count_suppressed=True,
        approximate_count=f"<{safe_threshold}",
        k_anon_ok=False,
        threshold=safe_threshold,
        petition_route=PETITION_ROUTE,
        layer=layer if layer in {"L0", "L1", "L2"} else "L1",
        records=[],
    )
