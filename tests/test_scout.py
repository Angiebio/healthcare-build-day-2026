"""Scout must be structurally incapable of leaking a record.

The feature's whole defence is that the model is handed a whitelist rather than
a filtered passport. These tests attack that claim: they build a payload from a
realistic, hostile input containing every identifier we would never release, and
then assert none of it survives into what the model receives.

If this file fails, Scout does not ship.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.scout import build_payload, deterministic_brief, literature  # noqa: E402

# Everything a passport carries that must never reach a narrator.
FORBIDDEN = [
    "Harrington^Lucas", "CHB-99214", "20181104", "BR-7721",
    "1.3.12.2.1107.5.2.19", "bch:FT-3091",
    "atrial width of 12.4 mm on the left",   # an evidence snippet
    "Boston Children's Hospital",            # the raw facility string
]


def _hostile_nodes() -> list[dict]:
    """Node results carrying far more than Scout is entitled to."""
    return [
        {"node": "BCH", "label": "Boston Children's", "k_anon_ok": False,
         "records_returned": 7, "approximate_count": "<10",
         "passport_id": "bch:FT-3091", "patient_name": "Harrington^Lucas"},
        {"node": "MGH", "label": "Mass General", "k_anon_ok": True,
         "records_returned": 14, "mrn": "CHB-99214"},
        {"node": "BWH", "label": "Brigham", "k_anon_ok": True, "records_returned": 11},
    ]


def test_payload_contains_no_identifier_from_a_hostile_input() -> None:
    payload = build_payload(
        query="glioblastoma",
        per_node=_hostile_nodes(),
        stats=[{"quantity": "lesion_dimension", "n": 22, "mean": 3.4, "median": 3.1,
                "min": 1.2, "max": 7.8, "unit": "cm",
                "snippet": "atrial width of 12.4 mm on the left",
                "study_id": "BR-7721"}],
        concepts=["glioblastoma", "brain"],
    )
    blob = json.dumps(payload)
    leaks = [token for token in FORBIDDEN if token in blob]
    assert not leaks, f"Scout payload leaked: {leaks}"


def test_a_withheld_hospital_contributes_no_count() -> None:
    """The suppressed number must not reach the model even as context."""
    payload = build_payload("q", _hostile_nodes(), [], [])
    withheld = [h for h in payload["hospitals"] if "status" in h]

    assert withheld, "the withholding hospital must still be named"
    for hospital in withheld:
        assert "studies" not in hospital
        assert "7" not in json.dumps(hospital)
        assert "<10" not in json.dumps(hospital)


def test_payload_keys_are_a_closed_set() -> None:
    """Positive construction: new passport fields cannot appear by accident."""
    payload = build_payload("q", _hostile_nodes(),
                            [{"quantity": "x", "n": 1, "mean": 1, "median": 1,
                              "min": 1, "max": 1, "unit": "mm", "extra": "leak"}], ["c"])

    assert set(payload) == {"query", "hospitals", "measurements",
                            "clinical_concepts", "note"}
    for hospital in payload["hospitals"]:
        assert set(hospital) <= {"hospital", "studies", "status"}
    for measure in payload["measurements"]:
        assert set(measure) == {"quantity", "n", "mean", "median", "min", "max", "unit"}


def test_deterministic_brief_states_the_withholding_without_the_number() -> None:
    payload = build_payload("glioblastoma", _hostile_nodes(), [], [])
    text = deterministic_brief(payload)

    assert "Boston Children's" in text
    assert "withheld" in text
    assert " 7 " not in text and "<10" not in text
    assert text.count(".") >= 3          # three sentences, same shape as the model path


def test_literature_lookup_is_offline_and_degrades_quietly() -> None:
    hits = literature(["pediatric brain tumor"])
    assert isinstance(hits, list)
    for paper in hits:
        assert paper["url"].startswith("https://pubmed.ncbi.nlm.nih.gov/")

    assert literature(["a condition nobody has ever described"]) == []
    assert literature([]) == []
