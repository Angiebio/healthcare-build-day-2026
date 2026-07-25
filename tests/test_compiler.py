"""Release-boundary tests for Lantern's privacy-utility compiler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.compiler import compile_passport
from scripts.passport import Passport
from scripts.terminology import CURATED_CODE_SOURCES
from tools.build_fixtures import compile_passport as legacy_compile_passport


DATA = Path("C:/Users/ajohn/hackdata/provider-node/data")

pytestmark = pytest.mark.skipif(
    not DATA.exists(), reason="challenge corpus not present on this machine"
)


def _records(filename: str) -> list[dict[str, object]]:
    return json.loads((DATA / filename).read_text(encoding="utf-8"))


def _representative_record() -> dict[str, object]:
    return next(
        record
        for record in _records("bch_data.json")
        if record["BodyPartExamined"] == "FETAL"
        and "ventriculomegaly" in str(record["Diagnosis"]).casefold()
        and "atrial width" in str(record["Diagnosis"]).casefold()
    )


def _canonical_code(concept: dict[str, object]) -> str:
    prefixes = {"SCT": "SNOMED", "HPO": "HPO", "ORPHA": "ORPHA"}
    system = str(concept["system"])
    return f"{prefixes[system]}:{concept['code']}"


def test_compilation_is_deterministic_and_legacy_reexport_is_identical() -> None:
    record = _representative_record()
    first = compile_passport("BCH", record)
    second = compile_passport("BCH", record)

    assert first == second
    assert legacy_compile_passport("BCH", record) == first


def test_compiler_output_is_a_typed_passport_not_a_shape_convention() -> None:
    compiled = compile_passport("BCH", _representative_record())
    typed = Passport.model_validate(compiled)

    assert typed.passport_id == compiled["passport_id"]
    assert typed.owner.node == "BCH"
    assert typed.population.basis == "gestational"
    assert typed.deid_manifest.prose_withheld is True


def test_every_emitted_concept_traces_to_the_curated_terminology_map() -> None:
    compiled = compile_passport("BCH", _representative_record())
    emitted = [compiled["imaging"]["body_site"], *compiled["concepts"]]

    assert emitted
    assert any(concept["display"] == "ventriculomegaly" for concept in emitted)
    for concept in emitted:
        # Two honest provenances, and the distinction is the point. A concept
        # carrying a code was matched against the curated map, so that code must
        # trace to a cited source. A concept recognised in report text but not
        # coded says so: provenance report_extraction, code None. Emitting the
        # term uncoded is what makes the clinical vocabulary searchable at all,
        # and it is strictly better than inventing an identifier for it.
        if concept.get("code") is None:
            assert concept["provenance"] == "report_extraction"
            assert concept["display"].strip()
        else:
            assert concept["provenance"] == "curated"
            assert _canonical_code(concept) in CURATED_CODE_SOURCES


def test_uncoded_report_terms_are_searchable_but_never_fabricate_a_code() -> None:
    """The glioblastoma case: present in the report, absent from the coded map.

    Before this, such a term was dropped entirely, so a report could state
    glioblastoma and the passport carried nothing to find it by.
    """
    record = dict(_representative_record())
    record["BodyPartExamined"] = "BRAIN"
    record["Diagnosis"] = (
        "MR imaging of the brain demonstrates a heterogeneously enhancing "
        "intra-axial mass consistent with glioblastoma."
    )
    concepts = compile_passport("MGH", record)["concepts"]
    match = next((c for c in concepts if c["display"] == "glioblastoma"), None)

    assert match is not None, "recognised clinical terms must be indexed"
    assert match["code"] is None
    assert match["system"] is None
    assert match["provenance"] == "report_extraction"


def test_every_measurement_carries_release_evidence() -> None:
    compiled = compile_passport("BCH", _representative_record())

    assert compiled["measurements"]
    for measurement in compiled["measurements"]:
        assert measurement["provenance"] == "report_extraction"
        assert 0.0 <= measurement["confidence"] <= 1.0
        assert measurement["snippet"].strip()
        assert len(measurement["span"]) == 2


def test_manifest_matches_the_transformations_that_actually_occurred() -> None:
    record = _representative_record()
    compiled = compile_passport("BCH", record)
    manifest = compiled["deid_manifest"]
    serialized = json.dumps(compiled, ensure_ascii=False)

    removed_source_fields = {
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "InstitutionName",
        "StudyDate",
        "PatientAge",  # maternal age is discarded for a fetal study
    }
    assert set(manifest["removed"]) == removed_source_fields
    for field in removed_source_fields:
        assert record[field]
        assert str(record[field]) not in serialized

    assert manifest["generalized"] == [
        "Diagnosis gestational age→gestational weeks"
    ]
    assert manifest["hashed"] == ["StudyInstanceUID→pseudonym"]
    assert str(record["StudyInstanceUID"]) not in serialized
    assert manifest["pseudonym"].startswith("sha256:")
    assert manifest["prose_withheld"] is True
    assert str(record["Diagnosis"]) not in serialized


def test_invalid_node_fails_loud_before_any_passport_can_cross() -> None:
    with pytest.raises(ValueError, match="unknown hospital node"):
        compile_passport("UNKNOWN", _representative_record())
