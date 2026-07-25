"""The demo ladder is asserted, not hoped for.

Every number Angie says on stage is pinned here. If someone retunes the extractor
at 1:30 and a cohort silently moves, this test fails loudly at 1:31 instead of the
demo failing at 3:30. That is the whole point: a demo cohort is a contract, and an
untested contract is a rumour.

Ladder is CORRECTIONS-v2 Correction 1. Counts are UNIQUE STUDIES, not measurements
-- a bilateral finding yields two measurements inside one study, and conflating the
two is exactly how the first hero query got mis-sized.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "app" / "static" / "fixtures.json"

K_ANON = 10


@pytest.fixture(scope="module")
def passports() -> list[dict]:
    if not FIXTURES.exists():
        pytest.skip("fixtures.json not built -- run tools/build_fixtures.py")
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["passports"]


def _by_node(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in rows:
        out[p["owner"]["node"]] = out.get(p["owner"]["node"], 0) + 1
    return out


def _studies_where(passports, quantity, predicate, body_part=None) -> list[dict]:
    """Unique studies holding >=1 measurement of `quantity` satisfying `predicate`."""
    hits = []
    for p in passports:
        if body_part and p["imaging"]["body_part_raw"] != body_part:
            continue
        if any(m["quantity"] == quantity and predicate(m["value"]) for m in p["measurements"]):
            hits.append(p)
    return hits


# --------------------------------------------------------------------------
# Beat 1b -- ejection fraction < 40%. The robust opener: big, all three nodes.
# --------------------------------------------------------------------------
def test_beat_1b_reduced_ejection_fraction(passports):
    hits = [
        p for p in passports
        if any(
            m["quantity"].endswith("ejection_fraction") and m["value"] < 40
            for m in p["measurements"]
        )
    ]
    per_node = _by_node(hits)
    assert set(per_node) == {"BCH", "MGH", "BWH"}, "federation beat needs all three nodes"
    for node, n in per_node.items():
        assert n >= K_ANON, f"{node} must clear k={K_ANON} for the opener, got {n}"
    print(f"\n  beat 1b  EF<40%: {per_node}  total={len(hits)}")


# --------------------------------------------------------------------------
# Beat 2 -- fetal ventriculomegaly. The impossible query.
# --------------------------------------------------------------------------
def test_beat_2_fetal_ventriculomegaly_clears_k_anon(passports):
    hits = _studies_where(
        passports, "lateral_ventricular_atrial_width", lambda v: v > 10, body_part="FETAL"
    )
    per_node = _by_node(hits)
    assert set(per_node) == {"BCH", "MGH", "BWH"}, "hero query must hit all three nodes"
    for node, n in per_node.items():
        assert n >= K_ANON, f"{node} must clear k={K_ANON} so results actually render, got {n}"
    print(f"\n  beat 2   atrial width >10mm: {per_node}  total={len(hits)}")


def test_beat_2_bilateral_parsing_is_visible(passports):
    """A study with two atrial widths proves the parser isn't naive. Demo opens one."""
    bilateral = [
        p for p in passports
        if len([m for m in p["measurements"]
                if m["quantity"] == "lateral_ventricular_atrial_width"]) >= 2
    ]
    assert bilateral, "need >=1 bilateral study to show left/right splitting on stage"
    print(f"\n  bilateral studies available: {len(bilateral)}  e.g. {bilateral[0]['passport_id']}")


# --------------------------------------------------------------------------
# Beat 3 -- severe >15mm. Every node must FALL BELOW k and suppress.
# This is the one that must not drift: if a node creeps to 10 the privacy
# beat silently stops firing and we would not notice until we were on stage.
# --------------------------------------------------------------------------
def test_beat_3_severe_suppresses_at_every_node(passports):
    hits = _studies_where(
        passports, "lateral_ventricular_atrial_width", lambda v: v > 15, body_part="FETAL"
    )
    per_node = _by_node(hits)
    assert per_node, "severe tier cannot be empty -- there'd be nothing to suppress"
    for node, n in per_node.items():
        assert 0 < n < K_ANON, (
            f"{node} has {n} severe studies; the k-anon beat needs 0 < n < {K_ANON} "
            f"at every node or the demo shows results where it promised suppression"
        )
    print(f"\n  beat 3   atrial width >15mm: {per_node}  total={len(hits)} -> all suppress")


# --------------------------------------------------------------------------
# The differencing exploit the champion brief invites a judge to try.
# Both queries individually clear k; their difference does not.
# --------------------------------------------------------------------------
def test_differencing_exploit_still_reproduces(passports):
    """CORRECTION-6 NOTE: the pair named in the corrections doc (>10mm vs <=24wk)
    deltas 160 against TV's shipped extractor -- nowhere near k. It was sized off an
    earlier, narrower regex. This is the pair that actually reproduces, re-derived
    from the built fixtures. If a judge is invited to break it live, THIS is the
    sequence to hand them."""

    def bch_fetal(mm_gt, gest_max=None):
        rows = []
        for p in passports:
            if p["imaging"]["body_part_raw"] != "FETAL" or p["owner"]["node"] != "BCH":
                continue
            vals = [m["value"] for m in p["measurements"]
                    if m["quantity"] == "lateral_ventricular_atrial_width"]
            if not vals or max(vals) <= mm_gt:
                continue
            if gest_max is not None:
                weeks = p["population"].get("gestational_age_weeks")
                if weeks is None or weeks > gest_max:
                    continue
            rows.append(p)
        return rows

    broad, narrow = len(bch_fetal(12)), len(bch_fetal(12, 31))
    delta = broad - narrow
    assert broad >= K_ANON and narrow >= K_ANON, "both probes must be individually permitted"
    assert 0 < delta < K_ANON, (
        f"exploit no longer reproduces (delta={delta}); re-derive a pair with "
        f"tools/find_exploit or cut the 'try to break it' invitation from the brief"
    )
    print(f"\n  exploit  BCH >12mm={broad}  +<=31wk={narrow}  delta={delta} -> below k, leaks")


# --------------------------------------------------------------------------
# Fetal population axis must be gestational, never the mother's age.
# --------------------------------------------------------------------------
def test_fetal_studies_never_banded_on_maternal_age(passports):
    fetal = [p for p in passports if p["imaging"]["body_part_raw"] == "FETAL"]
    assert fetal
    wrong = [
        p for p in fetal
        if p["population"]["basis"] == "chronological"
        and p["population"]["pediatric_stage"] in {"adult", "adolescent"}
    ]
    assert not wrong, (
        f"{len(wrong)} fetal studies banded on maternal age -- a fetus labelled "
        f"'adult' in the UI is the kind of thing a fetal-medicine judge sees instantly"
    )


def test_no_prose_field_on_any_passport(passports):
    """The trust boundary, asserted. Snippets are permitted; whole reports are not."""
    for p in passports[:500]:
        assert "Diagnosis" not in p and "report" not in p
        assert p["privacy"]["free_text_released"] is False
