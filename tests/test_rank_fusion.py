"""Tests for explainable, gracefully degrading rank fusion."""

from __future__ import annotations

import pytest

from scripts.rank_fusion import fuse


def test_missing_embedding_signal_degrades_gracefully() -> None:
    results = fuse(
        rankings={
            "lexical": [("study-a", 9.2), ("study-b", 8.7)],
            "concept_ontology": [("study-b", 1.0), ("study-c", 0.9)],
            "numeric_proximity": [("study-b", 0.99), ("study-a", 0.8)],
        },
        weights={
            "lexical": 1.0,
            "concept_ontology": 1.0,
            "numeric_proximity": 1.25,
        },
    )

    assert [result.study_id for result in results] == ["study-b", "study-a", "study-c"]
    assert "embedding" not in results[0].why["signals"]
    assert results[0].why["reason"] == (
        "matched: concept ontology · lexical · numeric proximity"
    )


def test_ties_are_deterministic_by_study_id() -> None:
    rankings = {
        "lexical": [("study-b", 1.0), ("study-a", 1.0)],
        "numeric": [("study-a", 1.0), ("study-b", 1.0)],
    }
    weights = {"lexical": 1.0, "numeric": 1.0}
    first = fuse(rankings, weights)
    second = fuse(rankings, weights)

    assert [item.study_id for item in first] == ["study-a", "study-b"]
    assert first == second


def test_bad_weights_and_duplicate_ids_fail_loud() -> None:
    with pytest.raises(ValueError, match="missing fusion weight"):
        fuse({"lexical": [("study-a", 1.0)]}, {})
    with pytest.raises(ValueError, match="duplicate"):
        fuse(
            {"lexical": [("study-a", 1.0), ("study-a", 0.5)]},
            {"lexical": 1.0},
        )
