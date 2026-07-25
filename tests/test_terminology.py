"""T-18 tests: terminology must fire on the actual three-node corpus."""

from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.query_ast import compile_query
from scripts.terminology import (
    CURATED_CODE_SOURCES,
    CURATED_SURFACE_TERMS,
    Concept,
    CuratedTerminology,
    expand_query_concepts,
)


def _relationships(term: str) -> dict[str, str]:
    return {
        concept.display: concept.relationship
        for concept in CuratedTerminology().lookup(term)
    }


def _provider_data() -> Path:
    configured = os.environ.get("LANTERN_PROVIDER_DATA")
    path = (
        Path(configured)
        if configured
        else Path("C:/Users/ajohn/hackdata/provider-node/data")
    )
    assert path.is_dir(), (
        "real provider corpus missing; set LANTERN_PROVIDER_DATA to its data directory"
    )
    return path


def _diagnoses() -> list[str]:
    diagnoses: list[str] = []
    for path in sorted(_provider_data().glob("*.json")):
        records = json.loads(path.read_text(encoding="utf-8"))
        diagnoses.extend(record["Diagnosis"] for record in records)
    assert len(diagnoses) == 2_700
    return diagnoses


def test_tumor_reaches_literal_challenge_terms_with_correct_relationships() -> None:
    relationships = _relationships("pediatric brain tumor")
    assert relationships["tumor"] == "exact"
    assert relationships["neoplasm"] == "synonym"
    assert relationships["glioma"] == "descendant"
    assert relationships["low-grade glioma"] == "descendant"


def test_ventriculomegaly_reaches_hero_query_cluster() -> None:
    relationships = _relationships("ventriculomegaly")
    assert relationships["ventricular dilatation"] == "synonym"
    assert relationships["hydrocephalus"] == "related"
    assert relationships["enlarged lateral ventricles"] == "synonym"
    assert relationships["lateral ventricular atrial width"] == "related"


def test_expansion_increases_hits_on_real_three_node_corpus() -> None:
    diagnoses = [diagnosis.casefold() for diagnosis in _diagnoses()]
    baseline = sum("tumor" in diagnosis for diagnosis in diagnoses)

    expanded = CuratedTerminology().lookup("tumor")
    alternatives = {
        concept.display.casefold()
        for concept in expanded
        if concept.relationship != "exact"
    }
    expanded_hits = sum(
        "tumor" in diagnosis
        or any(alternative in diagnosis for alternative in alternatives)
        for diagnosis in diagnoses
    )

    assert baseline == 26
    assert expanded_hits > baseline
    assert any(
        "glioma" in diagnosis and "tumor" not in diagnosis for diagnosis in diagnoses
    )


def test_query_ast_expansion_is_validated_deduplicated_and_explainable() -> None:
    ast = compile_query(
        None,
        {
            "imaging": {"modality": ["MR"], "body_site": ["BRAIN"]},
            "clinical": {
                "text_terms": ["pediatric brain tumor"],
                "expand_ontology": True,
            },
        },
    )
    expanded = expand_query_concepts(ast, CuratedTerminology())

    assert "glioma" in expanded.clinical.text_terms
    assert "neoplasm" in expanded.clinical.text_terms
    assert len(expanded.clinical.text_terms) == len(
        {term.casefold() for term in expanded.clinical.text_terms}
    )
    assert any(
        trace.source == "pediatric brain tumor"
        and trace.expanded_to == "glioma"
        and trace.relationship == "descendant"
        for trace in expanded.ontology_expansion
    )


def test_expansion_disabled_preserves_query_and_records_nothing() -> None:
    ast = compile_query(
        None,
        {
            "clinical": {
                "text_terms": ["tumor"],
                "expand_ontology": False,
            }
        },
    )
    expanded = expand_query_concepts(ast, CuratedTerminology())
    assert expanded.clinical.text_terms == ["tumor"]
    assert expanded.ontology_expansion == []


def test_unknown_term_and_code_return_empty_without_raising() -> None:
    service = CuratedTerminology()
    assert service.lookup("quantum whisker disorder") == []
    assert service.synonyms("quantum whisker disorder") == []
    assert service.expand("HPO:9999999") == []


def test_every_emitted_code_is_present_in_the_cited_curated_map() -> None:
    service = CuratedTerminology()
    emitted = {
        concept.code
        for term in CURATED_SURFACE_TERMS
        for concept in service.lookup(term)
        if concept.code is not None
    }
    assert emitted
    assert emitted <= CURATED_CODE_SOURCES.keys()


def test_direction_validation_fails_loud() -> None:
    service = CuratedTerminology()
    assert service.expand("HPO:0002119", direction="descendants")

    try:
        service.expand("HPO:0002119", direction="sideways")
    except ValueError as exc:
        assert "direction" in str(exc)
    else:
        raise AssertionError("invalid expansion direction did not fail loud")


def test_swapped_provider_cannot_smuggle_unvalidated_code_into_ast() -> None:
    class BadTerminology:
        def lookup(self, term: str) -> list[Concept]:
            return [
                Concept(
                    system="ORPHA",
                    code="ORPHA:NOT-VALIDATED",
                    display="invented disorder",
                    relationship="related",
                    provenance="curated",
                )
            ]

        def expand(self, code: str, *, direction: str = "both") -> list[Concept]:
            return []

        def synonyms(self, term: str) -> list[str]:
            return []

    ast = compile_query(
        None,
        {"clinical": {"text_terms": ["tumor"], "expand_ontology": True}},
    )
    try:
        expand_query_concepts(ast, BadTerminology())
    except ValueError as exc:
        assert "outside the validated AST" in str(exc)
    else:
        raise AssertionError("unvalidated terminology code crossed the AST boundary")
