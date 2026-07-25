"""Lantern's privacy-utility compiler and hospital trust boundary.

This is the only code permitted to see a raw patient record. It compiles that
record inside the hospital node into a typed, de-identified ``Passport``. The
serialized Passport returned here is the definition of what may leave that
node; raw identifiers and full report prose are structurally absent.

The function stays deterministic and side-effect free. Reading source records,
serving Passports, applying disclosure policy, and writing fixture artifacts
belong to callers outside this module.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any, Final

from .age_band import pediatric_stage, public_age_band, to_age_years
from .measure_extract import extract_measurements
from .passport import CodedConcept, Passport
from .terminology import Concept, CuratedTerminology

NODE_LABELS: Final[dict[str, str]] = {
    "BCH": "Boston Children's",
    "MGH": "Mass General",
    "BWH": "Brigham & Women's",
}

# Gestational age is the population axis for fetal studies. PatientAge on a
# fetal record is the mother's age, so it must never drive pediatric banding.
GEST: Final[re.Pattern[str]] = re.compile(
    r"(\d+(?:\.\d+)?)\s*weeks?\s+gestation", re.IGNORECASE
)

BODY_SITE_TERMS: Final[dict[str, str]] = {
    "BRAIN": "brain",
    "HEART": "heart",
    "FETAL": "fetal structure",
}

# These are the report conditions for which today's curated terminology graph
# carries verified codes. Unverified terms stay uncoded rather than fabricated.
CODED_REPORT_TERMS: Final[tuple[str, ...]] = (
    "ventriculomegaly",
    "hydrocephalus",
    "atrial septal defect",
    "ventricular septal defect",
)

REMOVED: Final[tuple[str, ...]] = (
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "InstitutionName",
    "StudyDate",
)

_TERMINOLOGY: Final[CuratedTerminology] = CuratedTerminology()


def pseudonym(node: str, study_id: str) -> str:
    """Return a stable one-way linkage token scoped to one hospital node."""

    return "sha256:" + hashlib.sha256(
        f"lantern|{node}|{study_id}".encode("utf-8")
    ).hexdigest()[:16]


def compile_passport(node: str, rec: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one raw provider record into a validated JSON-ready Passport."""

    if node not in NODE_LABELS:
        raise ValueError(f"unknown hospital node {node!r}")
    if not isinstance(rec, Mapping):
        raise TypeError("rec must be a mapping")

    body = str(rec.get("BodyPartExamined") or "").upper()
    report = str(rec.get("Diagnosis") or "")
    measurements = [measurement.to_dict() for measurement in extract_measurements(report)]

    # Prefer the extractor because it recognizes more corpus phrasing. The
    # narrow regex remains a deterministic fallback, never a guessed value.
    weeks = next(
        (
            measurement["value"]
            for measurement in measurements
            if measurement["quantity"] == "gestational_age_weeks"
        ),
        None,
    )
    if weeks is None:
        gestation_match = GEST.search(report)
        weeks = float(gestation_match.group(1)) if gestation_match else None

    if body == "FETAL":
        population = {
            "basis": "gestational" if weeks is not None else "unknown",
            "gestational_age_weeks": weeks,
            "pediatric_stage": "fetal",
            "public_age_band": "fetal",
            "sex": rec.get("PatientSex"),
        }
    else:
        years = to_age_years(str(rec.get("PatientAge") or ""))
        population = {
            "basis": "chronological",
            "gestational_age_weeks": None,
            "pediatric_stage": pediatric_stage(years) if years is not None else "unknown",
            "public_age_band": public_age_band(years) if years is not None else "unknown",
            "sex": rec.get("PatientSex"),
        }

    quantities = sorted({str(measurement["quantity"]) for measurement in measurements})
    removed = [field for field in REMOVED if rec.get(field)]
    if body == "FETAL" and rec.get("PatientAge"):
        # The corpus field is maternal age, not fetal age. It is discarded;
        # gestational age is independently extracted from the report.
        removed.append("PatientAge")
    body_site = _body_site_concept(body)
    concepts = _report_concepts(report)
    pseudonym_source = str(rec.get("StudyInstanceUID") or rec.get("StudyID"))

    candidate = {
        "passport_id": f"{node.lower()}:{rec.get('StudyID')}",
        "owner": {
            "node": node,
            "label": NODE_LABELS[node],
            "request_route": "/petition",
        },
        "imaging": {
            "modality": rec.get("Modality"),
            "body_site": body_site,
            "body_part_raw": body,
        },
        "population": population,
        "measurements": measurements,
        "concepts": concepts,
        "computational_readiness": {
            "has_quantitative_measurements": bool(measurements),
            "measurement_count": len(measurements),
            "quantities_available": quantities,
            "supports_quantitative_cohort_analysis": bool(measurements),
            "supports_threshold_stratification": bool(measurements),
            "missing_for_full_computability": [
                "voxel_geometry",
                "acquisition_parameters",
                "pixel_data",
            ],
        },
        "privacy": {
            "highest_release_layer": "L1",
            "patient_identity_removed": True,
            "release_status": "CONTROLLED_DERIVATIVE",
            "free_text_released": False,
        },
        "deid_manifest": {
            "removed": removed,
            "generalized": (
                ["Diagnosis gestational age→gestational weeks"]
                if population["basis"] == "gestational"
                else (["PatientAge→band"] if rec.get("PatientAge") else [])
            ),
            "hashed": [
                (
                    "StudyInstanceUID→pseudonym"
                    if rec.get("StudyInstanceUID")
                    else "StudyID→pseudonym"
                )
            ],
            "prose_withheld": True,
            "pseudonym": pseudonym(node, pseudonym_source),
        },
        "provenance": {
            "pipeline_version": "0.2.0-compiler",
            "source": "provider-node challenge corpus",
        },
    }

    # Validation is the release gate. If the real data and the Passport contract
    # disagree, compilation fails here rather than leaking a convention-shaped dict.
    passport = Passport.model_validate(candidate)
    return passport.model_dump(mode="json", by_alias=True)


def _body_site_concept(body: str) -> dict[str, Any]:
    surface = BODY_SITE_TERMS.get(body)
    if surface is None:
        return CodedConcept(
            display=body.title() or "Unknown",
            provenance="curated",
        ).model_dump(mode="json")

    exact = next(
        (
            concept
            for concept in _TERMINOLOGY.lookup(surface)
            if concept.relationship == "exact" and concept.code is not None
        ),
        None,
    )
    if exact is None:
        raise RuntimeError(f"terminology map has no coded body-site concept for {body}")
    return _passport_concept(exact)


def _report_concepts(report: str) -> list[dict[str, Any]]:
    normalized = report.casefold()
    concepts: list[dict[str, Any]] = []
    emitted_codes: set[str] = set()
    for term in CODED_REPORT_TERMS:
        if term not in normalized:
            continue
        exact = next(
            (
                concept
                for concept in _TERMINOLOGY.lookup(term)
                if concept.relationship == "exact" and concept.code is not None
            ),
            None,
        )
        if exact is None or exact.code in emitted_codes:
            continue
        emitted_codes.add(exact.code)
        concepts.append(_passport_concept(exact))
    return concepts


def _passport_concept(concept: Concept) -> dict[str, Any]:
    if concept.code is None or concept.system is None:
        raise ValueError("only verified coded concepts may enter a Passport")
    bare_code = concept.code.split(":", 1)[-1]
    return CodedConcept(
        system=concept.system,
        code=bare_code,
        display=concept.display,
        provenance="curated",
        relationship=concept.relationship,
    ).model_dump(mode="json")
