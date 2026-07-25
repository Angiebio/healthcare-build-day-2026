"""Reproducibility and numbers-lock tests for the honest delta evaluation."""

from __future__ import annotations

from pathlib import Path

from evals.delta import NUMBER_LOCK, evaluate, render_results


def test_delta_is_reproducible() -> None:
    assert render_results() == render_results()
    results_file = Path(__file__).parents[1] / "evals" / "RESULTS.md"
    assert results_file.read_text(encoding="utf-8") == render_results()


def test_numeric_ground_truth_matches_locked_node_counts() -> None:
    results = evaluate()
    for query_key, expected in NUMBER_LOCK.items():
        assert {
            node: results[query_key][node]["truth_count"]
            for node in ("BCH", "MGH", "BWH")
        } == expected


def test_numeric_thresholds_are_not_misreported_as_zero_recall() -> None:
    rendered = render_results()
    assert rendered.count("N/A — not expressible") >= 6
    assert "Literal keyword search is a strong, cheap precision tool" in rendered
