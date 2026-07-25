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

import json
import sys
from collections import Counter
from pathlib import Path

if sys.version_info[:2] != (3, 12):  # Jim's fail-loud guard -- scream early, not mid-import.
    raise SystemExit(f"Lantern targets Python 3.12; got {sys.version.split()[0]}")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.compiler import (  # noqa: E402,F401
    GEST,
    REMOVED,
    compile_passport,
    pseudonym,
)

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
