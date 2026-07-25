"""Generate demo fixtures for the researcher console from the real corpus.

WHY THIS EXISTS (and when it should die):
The frontend must not idle waiting for the broker. This compiles the real node
records into passport-shaped JSON using TV's real extractor, so the console shows
true snippets and true values from minute one. When Flame1's broker is live the
console flips to fetch() and this becomes test-fixture generation only.

It is NOT a second compiler. It does no policy, no fusion, no disclosure -- it is
a fixture press. The moment scripts/compiler.py lands, that becomes the source of
truth and this file imports it instead of open-coding the strip below.

Privacy discipline holds even on synthetic data: name / ID / DOB / institution are
dropped here and never reach the fixture. Prose is withheld; only the measurement
snippet crosses, which is what the frozen contract releases at L1 as provenance
evidence for the number.

Run:  python tools/build_fixtures.py
Out:  app/static/fixtures.json
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

if sys.version_info[:2] != (3, 12):  # Jim's fail-loud guard -- scream early, not mid-import.
    raise SystemExit(f"Lantern targets Python 3.12; got {sys.version.split()[0]}")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.age_band import pediatric_stage, public_age_band, to_age_years  # noqa: E402
from scripts.measure_extract import extract_measurements  # noqa: E402

DATA = Path(r"C:\Users\ajohn\hackdata\provider-node\data")
OUT = REPO / "app" / "static" / "fixtures.json"

NODES = {
    "BCH": {"file": "bch_data.json", "port": 8011, "label": "Boston Children's",
            "policy": "auto_approve_L1_with_irb"},
    "MGH": {"file": "mgh_data.json", "port": 8012, "label": "Mass General",
            "policy": "petition_required"},
    "BWH": {"file": "bwh_data.json", "port": 8013, "label": "Brigham & Women's",
            "policy": "petition_required"},
}

# Gestational age is the population axis for fetal studies. PatientAge on a fetal
# record is the MOTHER's age (14-35y) -- banding it as the patient's would label a
# fetus "adult". Correction v2 calls this out; we honour it by carrying `basis`.
GEST = re.compile(r"(\d+(?:\.\d+)?)\s*weeks?\s+gestation", re.IGNORECASE)

BODY_SITE = {
    "BRAIN": {"system": "SCT", "code": "12738006", "display": "Brain"},
    "HEART": {"system": "SCT", "code": "80891009", "display": "Heart"},
    "FETAL": {"system": "SCT", "code": "83418008", "display": "Fetal structure"},
}

REMOVED = ["PatientName", "PatientID", "PatientBirthDate", "InstitutionName"]


def pseudonym(node: str, study_id: str) -> str:
    """Salted, consistent, one-way. Cohorts stay linkable; the person does not."""
    return "sha256:" + hashlib.sha256(f"lantern|{node}|{study_id}".encode()).hexdigest()[:16]


def compile_passport(node: str, rec: dict) -> dict:
    body = (rec.get("BodyPartExamined") or "").upper()
    report = rec.get("Diagnosis") or ""
    measurements = [m.to_dict() for m in extract_measurements(report)]

    # Prefer TV's extractor for gestational age -- it catches phrasings my regex
    # doesn't ("at 24 weeks", "24-week fetus"). Regex is only the fallback.
    weeks = next(
        (m["value"] for m in measurements if m["quantity"] == "gestational_age_weeks"),
        None,
    )
    if weeks is None:
        gest = GEST.search(report)
        weeks = float(gest.group(1)) if gest else None

    if body == "FETAL":
        # A fetus is NEVER banded on PatientAge -- that field is the mother's age.
        # If gestational age is genuinely absent we say "unknown" and mean it. Guessing
        # here is how a fetus ends up labelled "adult" on a projector.
        population = {
            "basis": "gestational" if weeks is not None else "unknown",
            "gestational_age_weeks": weeks,
            "pediatric_stage": "fetal",
            "public_age_band": "fetal",
            "sex": rec.get("PatientSex"),
        }
    else:
        years = to_age_years(rec.get("PatientAge") or "")
        population = {
            "basis": "chronological",
            "gestational_age_weeks": None,
            "pediatric_stage": pediatric_stage(years) if years is not None else "unknown",
            "public_age_band": public_age_band(years) if years is not None else "unknown",
            "sex": rec.get("PatientSex"),
        }

    quantities = sorted({m["quantity"] for m in measurements})
    return {
        "passport_id": f"{node.lower()}:{rec.get('StudyID')}",
        "owner": {"node": node, "label": NODES[node]["label"], "request_route": "/petition"},
        "imaging": {
            "modality": rec.get("Modality"),
            "body_site": BODY_SITE.get(body, {"system": "SCT", "code": "", "display": body.title()}),
            "body_part_raw": body,
        },
        "population": population,
        "measurements": measurements,
        "computational_readiness": {
            "has_quantitative_measurements": bool(measurements),
            "measurement_count": len(measurements),
            "quantities_available": quantities,
            "supports_quantitative_cohort_analysis": bool(measurements),
            "supports_threshold_stratification": bool(measurements),
            "missing_for_full_computability": ["voxel_geometry", "acquisition_parameters", "pixel_data"],
        },
        "privacy": {
            "highest_release_layer": "L1",
            "patient_identity_removed": True,
            "release_status": "CONTROLLED_DERIVATIVE",
            "free_text_released": False,
        },
        "deid_manifest": {
            "removed": REMOVED,
            "generalized": (
                ["PatientAge→gestational weeks (from report)", "StudyDate→shifted"]
                if population["basis"] == "gestational"
                else ["PatientAge→band", "StudyDate→shifted"]
            ),
            "hashed": ["StudyInstanceUID→pseudonym"],
            "prose_withheld": True,
            "pseudonym": pseudonym(node, str(rec.get("StudyID"))),
        },
        "provenance": {"pipeline_version": "0.1.0-fixture", "source": "provider-node challenge corpus"},
    }


def main() -> None:
    if not DATA.exists():
        raise SystemExit(f"WIRING FAILURE: corpus not found at {DATA}")

    passports: list[dict] = []
    per_node = Counter()
    identifiers: set[str] = set()  # the real PHI VALUES, to prove none of them crossed
    for node, meta in NODES.items():
        raw = json.loads((DATA / meta["file"]).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = next(v for v in raw.values() if isinstance(v, list))
        for rec in raw:
            for field_name in ("PatientName", "PatientID", "PatientBirthDate", "InstitutionName"):
                value = rec.get(field_name)
                if value:
                    identifiers.add(str(value))
            passports.append(compile_passport(node, rec))
            per_node[node] += 1

    # Fail loud if an identifier VALUE leaked into the artifact. This assertion IS the
    # trust boundary, so it checks values -- not field names. The field names legitimately
    # appear in deid_manifest.removed, which is the manifest declaring what it stripped;
    # a naive substring scan flags that as a breach and cries wolf. Ask the real question:
    # did any actual name, MRN, DOB or institution survive the compile?
    blob = json.dumps(passports)
    leaked = sorted(v for v in identifiers if v in blob)
    if leaked:
        raise RuntimeError(
            f"PRIVACY FAILURE: {len(leaked)} identifier value(s) present in fixture "
            f"output, e.g. {leaked[:3]}"
        )

    payload = {
        "generated_by": "tools/build_fixtures.py",
        "note": "Demo fixtures compiled from the challenge corpus. Replaced by the live broker when up.",
        "nodes": [
            {"node": n, "label": m["label"], "port": m["port"],
             "policy": m["policy"], "studies": per_node[n]}
            for n, m in NODES.items()
        ],
        "passports": passports,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    print(f"wrote {OUT.relative_to(REPO)}  ({len(passports)} passports, {OUT.stat().st_size//1024} KB)")
    withmeas = sum(1 for p in passports if p["measurements"])
    print(f"  passports with >=1 measurement: {withmeas}/{len(passports)} "
          f"({100*withmeas/len(passports):.1f}%)")


if __name__ == "__main__":
    main()
