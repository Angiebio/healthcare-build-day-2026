"""Does PHI actually stay inside the hospital? Prove it, don't assert it.

Technical: adversarial scan of every compiled passport for any trace of the
identifiers present in the raw source records.
Philosophical: this is the test that has to exist. Our entire pitch rests on
one sentence -- "the prose never leaves the node" -- and a claim about privacy
that nobody tried to falsify is not evidence, it is advertising. So this file
goes looking for our own failure, over all 2,700 records, on purpose.

If this suite ever fails, we do not ship the demo. Nothing else in the repo
outranks it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.build_fixtures import compile_passport  # noqa: E402

# The corpus lives outside the repo (it is the challenge's data, not ours to
# redistribute). Skip cleanly rather than fail if a teammate lacks it.
DATA_DIR = Path(r"C:\Users\ajohn\hackdata\provider-node\data")
NODES = {"BCH": "bch_data.json", "MGH": "mgh_data.json", "BWH": "bwh_data.json"}

pytestmark = pytest.mark.skipif(
    not DATA_DIR.exists(), reason="challenge corpus not present on this machine"
)


def _records(node: str) -> list[dict]:
    return json.loads((DATA_DIR / NODES[node]).read_text(encoding="utf-8"))


def _blob(obj) -> str:
    """Flatten a passport to one searchable string.

    We serialise the WHOLE object rather than checking known fields, because the
    interesting failure is the one we didn't think to look for -- a name that
    survived inside a snippet, a nested dict, a debug field someone added at
    2pm. Structure-agnostic search is the only kind that catches that.
    """
    return json.dumps(obj, ensure_ascii=False, default=str)


@pytest.mark.parametrize("node", sorted(NODES))
def test_no_direct_identifier_survives_compilation(node: str) -> None:
    """No patient name, MRN, or birth date may appear anywhere in a passport."""
    leaks: list[str] = []

    for rec in _records(node):
        blob = _blob(compile_passport(node, rec))

        # Patient names arrive DICOM-style: "Harrington^Lucas". Check the whole
        # form and each component -- a surname alone is still an identifier.
        raw_name = rec.get("PatientName", "")
        for part in [raw_name, *raw_name.split("^")]:
            part = part.strip()
            # Skip trivially short tokens; they generate false positives against
            # ordinary clinical words and would make this test useless noise.
            if len(part) < 4:
                continue
            if re.search(rf"\b{re.escape(part)}\b", blob, re.IGNORECASE):
                leaks.append(f"{rec['StudyID']}: name fragment {part!r}")

        for field in ("PatientID", "PatientBirthDate"):
            value = str(rec.get(field, "")).strip()
            if value and value in blob:
                leaks.append(f"{rec['StudyID']}: {field} {value!r}")

    assert not leaks, (
        f"{node}: {len(leaks)} identifier leak(s) crossed the trust boundary. "
        f"First 5: {leaks[:5]}"
    )


@pytest.mark.parametrize("node", sorted(NODES))
def test_report_prose_is_not_republished(node: str) -> None:
    """Snippets may cross; the report may not.

    We deliberately DO release short evidence snippets -- a researcher must be
    able to see the sentence a number came from, or the number is unauditable.
    The line we hold is that a snippet is an excerpt, not a copy. This test
    enforces that distinction quantitatively so "we don't release the prose"
    stays true as the extractor evolves.
    """
    offenders: list[str] = []

    for rec in _records(node):
        report = rec.get("Diagnosis", "")
        blob = _blob(compile_passport(node, rec))

        if len(report) > 200 and report[:200] in blob:
            offenders.append(f"{rec['StudyID']}: verbatim report opening republished")

        # No single released fragment may approach the size of the report.
        for snippet in re.findall(r'"snippet":\s*"([^"]*)"', blob):
            if len(snippet) > 240:
                offenders.append(
                    f"{rec['StudyID']}: snippet of {len(snippet)} chars is an excerpt in name only"
                )

    assert not offenders, f"{node}: {offenders[:5]}"


@pytest.mark.parametrize("node", sorted(NODES))
def test_institution_is_generalized_not_leaked(node: str) -> None:
    """A node is identified by its short label, never by the raw facility string.

    'Boston Children's Hospital' as free text is a re-identification vector when
    combined with a rare finding and an age band. The node label is a routing
    address; the facility name is data about a patient's location of care.
    """
    for rec in _records(node):
        raw_institution = rec.get("InstitutionName", "")
        if not raw_institution:
            continue
        blob = _blob(compile_passport(node, rec))
        assert raw_institution not in blob, (
            f"{node} {rec['StudyID']}: raw InstitutionName {raw_institution!r} survived"
        )


@pytest.mark.parametrize("node", sorted(NODES))
def test_manifest_tells_the_truth(node: str) -> None:
    """The de-identification manifest must describe what actually happened.

    An inaccurate manifest is worse than no manifest: it invites a privacy
    office to trust a transformation that did not occur. So we check the
    evidence against the artifact rather than taking the artifact's word.
    """
    for rec in _records(node)[:120]:  # sampling is fine; this is a consistency check
        passport = compile_passport(node, rec)
        manifest = passport.get("deid_manifest", {})
        declared = set(manifest.get("removed", [])) | set(
            manifest.get("generalized", [])
        ) | set(manifest.get("pseudonymized", []))

        for field in ("PatientName", "PatientID", "PatientBirthDate", "InstitutionName"):
            if rec.get(field):
                assert field in declared, (
                    f"{node} {rec['StudyID']}: {field} was present in the source and is "
                    f"absent from the passport, but the manifest never declares handling it. "
                    f"Silent removal is still undocumented processing."
                )

        assert manifest.get("prose_withheld") is True, (
            f"{node} {rec['StudyID']}: manifest must affirm the report text was withheld"
        )


def test_fetal_age_is_never_reported_as_chronological() -> None:
    """A fetus must never be described using the mother's age.

    This is the correctness bug Flame2 found in his own code, promoted to a
    permanent guard. The recorded PatientAge on a fetal study is the mother's;
    banding it chronologically renders a fetus as an adult. A fetal-medicine
    clinician spots that instantly, and then rightly distrusts every other
    number on the page. Cheap bug, expensive consequence.
    """
    violations: list[str] = []

    for node in NODES:
        for rec in _records(node):
            if rec.get("BodyPartExamined") != "FETAL":
                continue
            population = compile_passport(node, rec).get("population", {})
            basis = population.get("basis")

            if basis == "chronological":
                violations.append(f"{node} {rec['StudyID']}: fetal study banded chronologically")
            if population.get("pediatric_stage") == "adult":
                violations.append(f"{node} {rec['StudyID']}: fetus labelled 'adult'")

    assert not violations, f"{len(violations)} fetal age errors. First 5: {violations[:5]}"
