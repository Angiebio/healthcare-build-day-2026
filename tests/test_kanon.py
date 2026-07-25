"""Adversarial tests for the fail-closed disclosure gate."""

from __future__ import annotations

import scripts.kanon as kanon


def _passports(count: int) -> list[dict[str, str]]:
    return [{"study_id": f"study-{index}"} for index in range(count)]


def test_below_threshold_suppresses_records() -> None:
    disclosure = kanon.apply_disclosure(_passports(9), threshold=10, layer="L1")

    assert disclosure.count_suppressed is True
    assert disclosure.approximate_count == "<10"
    assert disclosure.k_anon_ok is False
    assert disclosure.threshold == 10
    assert disclosure.records == []
    assert disclosure.petition_route


def test_at_threshold_releases_records() -> None:
    disclosure = kanon.apply_disclosure(_passports(10), threshold=10, layer="L1")

    assert disclosure.count_suppressed is False
    assert disclosure.approximate_count == "10"
    assert disclosure.k_anon_ok is True
    assert len(disclosure.records) == 10


def test_internal_error_fails_closed(monkeypatch) -> None:
    def explode(_results):
        raise RuntimeError("simulated internal counting failure")

    monkeypatch.setattr(kanon, "_count_results", explode)
    disclosure = kanon.apply_disclosure(_passports(20), threshold=10, layer="L2")

    assert disclosure.count_suppressed is True
    assert disclosure.k_anon_ok is False
    assert disclosure.records == []


def test_invalid_policy_and_malformed_passport_fail_closed() -> None:
    assert kanon.apply_disclosure(_passports(20), threshold=0).k_anon_ok is False
    assert kanon.apply_disclosure(_passports(20), layer="ROOT").k_anon_ok is False
    assert kanon.apply_disclosure([{"study_id": "ok"}, object()]).k_anon_ok is False  # type: ignore[list-item]
