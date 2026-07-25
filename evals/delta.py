"""Offline, deterministic comparison of Lantern with fair keyword search."""

from __future__ import annotations

from collections import defaultdict
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable, Iterable

if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"Lantern delta eval requires Python 3.12; got {sys.version.split()[0]}")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.age_band import to_age_years  # noqa: E402
from scripts.measure_extract import extract_measurements  # noqa: E402
from scripts.terminology import CuratedTerminology  # noqa: E402


NODE_ORDER = ("BCH", "MGH", "BWH")
NODE_FILES = {
    "BCH": "bch_data.json",
    "MGH": "mgh_data.json",
    "BWH": "bwh_data.json",
}
NUMBER_LOCK = {
    "ef_lt_40": {"BCH": 30, "MGH": 53, "BWH": 73},
    "atrial_gt_10": {"BCH": 87, "MGH": 78, "BWH": 60},
    "atrial_gt_15": {"BCH": 7, "MGH": 6, "BWH": 3},
}
_TOKEN = re.compile(r"[a-z0-9]+")
_EF_QUANTITIES = {
    "ejection_fraction",
    "left_ventricular_ejection_fraction",
    "right_ventricular_ejection_fraction",
}


def keyword_baseline(query_text: str, records: list[dict]) -> list[str]:
    """Return records matching every case-folded query token.

    Callers may first apply structured filters already available to ordinary
    hospital search (for example modality or body site). This function does not
    extract measurements, expand terminology, compare numbers, or infer a
    clinical synonym. It is intentionally a strong literal baseline, not a
    strawman.
    """

    if not isinstance(query_text, str) or not query_text.strip():
        raise ValueError("query_text must be a non-empty string")
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise TypeError("records must be a list of dictionaries")
    tokens = _TOKEN.findall(query_text.casefold())
    if not tokens:
        raise ValueError("query_text contains no searchable tokens")

    hits: list[str] = []
    for record in records:
        study_id = record.get("_study_id")
        if not isinstance(study_id, str):
            raise ValueError("every record requires an internal _study_id")
        searchable = " ".join(
            str(value)
            for key, value in sorted(record.items())
            if key not in {"_study_id", "_node", "_measurements"} and value is not None
        ).casefold()
        if all(token in searchable for token in tokens):
            hits.append(study_id)
    return sorted(hits)


def evaluate() -> dict[str, dict[str, dict[str, object]]]:
    """Compute all query/node comparisons and assert the locked truth counts."""

    records = _load_records()
    by_node = {
        node: [record for record in records if record["_node"] == node]
        for node in NODE_ORDER
    }
    expansion_terms = {
        concept.display.casefold()
        for concept in CuratedTerminology().lookup("tumor")
    }

    evaluations: dict[str, dict[str, dict[str, object]]] = {}
    definitions = (
        (
            "ef_lt_40",
            "Reduced EF <40%",
            lambda record: _has_measurement(record, _EF_QUANTITIES, lambda value: value < 40.0),
            lambda node_records: _union_keyword_hits(
                ("reduced ejection fraction", "low EF"), node_records
            ),
            True,
            "Reduced/low language is broad and noisy across cardiac findings; it also misses numeric-only phrasing.",
        ),
        (
            "atrial_gt_10",
            "Fetal atrial width >10 mm",
            lambda record: (
                record["BodyPartExamined"] == "FETAL"
                and _has_measurement(
                    record,
                    {"lateral_ventricular_atrial_width"},
                    lambda value: value > 10.0,
                )
            ),
            lambda node_records: set(
                keyword_baseline(
                    "ventriculomegaly",
                    [
                        record
                        for record in node_records
                        if record["BodyPartExamined"] == "FETAL"
                    ],
                )
            ),
            False,
            "Keywords can find named ventriculomegaly, but cannot execute the >10 mm threshold.",
        ),
        (
            "atrial_gt_15",
            "Severe fetal width >15 mm",
            lambda record: (
                record["BodyPartExamined"] == "FETAL"
                and _has_measurement(
                    record,
                    {"lateral_ventricular_atrial_width"},
                    lambda value: value > 15.0,
                )
            ),
            lambda node_records: set(
                keyword_baseline(
                    "severe ventriculomegaly",
                    [
                        record
                        for record in node_records
                        if record["BodyPartExamined"] == "FETAL"
                    ],
                )
            ),
            False,
            "The word severe often modifies another finding; keywords cannot order the measured width.",
        ),
        (
            "tumor_expansion",
            "Pediatric brain tumor + expansion",
            lambda record: (
                _is_pediatric_brain(record)
                and any(term in record["Diagnosis"].casefold() for term in expansion_terms)
            ),
            lambda node_records: set(
                keyword_baseline(
                    "tumor",
                    [record for record in node_records if _is_pediatric_brain(record)],
                )
            ),
            True,
            "Literal tumor search is highly precise and simpler; expansion earns recall at the cost of broader related terms.",
        ),
    )

    for key, label, truth_predicate, baseline_fn, recall_expressible, meaning in definitions:
        evaluations[key] = {}
        for node in NODE_ORDER:
            node_records = by_node[node]
            truth = {
                record["_study_id"]
                for record in node_records
                if truth_predicate(record)
            }
            baseline = baseline_fn(node_records)
            true_positive = len(truth & baseline)
            precision = true_positive / len(baseline) if baseline else None
            recall = true_positive / len(truth) if truth and recall_expressible else None
            evaluations[key][node] = {
                "label": label,
                "truth_count": len(truth),
                "baseline_hits": len(baseline),
                "true_positive": true_positive,
                "precision": precision,
                "recall": recall,
                "recall_expressible": recall_expressible,
                "meaning": meaning,
            }

    for query_key, expected in NUMBER_LOCK.items():
        observed = {
            node: int(evaluations[query_key][node]["truth_count"])
            for node in NODE_ORDER
        }
        if observed != expected:
            raise RuntimeError(
                f"NUMBERS LOCK FAILED for {query_key}: expected {expected}, observed {observed}"
            )
    return evaluations


def render_results() -> str:
    """Render stable Markdown suitable for stdout and RESULTS.md."""

    evaluations = evaluate()
    lines = [
        "# Lantern honest delta: keyword search vs. compiled facts",
        "",
        "| Intent | Node | Extractor-derived truth | Keyword hits | Baseline recall | Baseline precision | What it means |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for query_key in ("ef_lt_40", "atrial_gt_10", "atrial_gt_15", "tumor_expansion"):
        for node in NODE_ORDER:
            row = evaluations[query_key][node]
            recall = (
                _percent(row["recall"])
                if row["recall_expressible"]
                else "N/A — not expressible"
            )
            lines.append(
                f"| {row['label']} | {node} | {row['truth_count']} | "
                f"{row['baseline_hits']} | {recall} | {_percent(row['precision'])} | "
                f"{row['meaning']} |"
            )
    lines.extend(
        [
            "",
            "## Honest finding",
            "",
            "Literal keyword search is a strong, cheap precision tool when a report uses the expected words; "
            "for pediatric brain tumor it avoids the broader related terms admitted by our curated expansion. "
            "Lantern's advantage is not that keywords are bad—it is that keywords cannot execute numeric "
            "comparisons already trapped in prose.",
            "",
            "## Limitations",
            "",
            "- Ground truth is **extractor-derived**, not clinician-adjudicated.",
            "- The challenge corpus is synthetic and may not reproduce real institutional language or prevalence.",
            "- There is no independent annotator set; precision here measures agreement with Lantern's extracted result set.",
            "- Numeric-query recall is reported as **N/A — not expressible**, not zero, because literal search has no numeric comparator.",
            "- The terminology expansion is a small corpus-grounded map, not a production terminology server.",
            "",
            "## Reproduce offline",
            "",
            "```bash",
            r"python -B evals\delta.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _provider_data() -> Path:
    configured = os.environ.get("LANTERN_PROVIDER_DATA")
    return (
        Path(configured)
        if configured
        else Path(r"C:\Users\ajohn\hackdata\provider-node\data")
    )


def _load_records() -> list[dict]:
    root = _provider_data()
    if not root.is_dir():
        raise RuntimeError(
            f"provider corpus missing at {root}; set LANTERN_PROVIDER_DATA"
        )
    records: list[dict] = []
    for node in NODE_ORDER:
        path = root / NODE_FILES[node]
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise RuntimeError(f"{path} must contain a JSON array")
        for record in raw:
            if not isinstance(record, dict):
                raise RuntimeError(f"{path} contains a non-object record")
            enriched = dict(record)
            enriched["_node"] = node
            enriched["_study_id"] = f"{node}:{record['StudyID']}"
            enriched["_measurements"] = extract_measurements(record["Diagnosis"])
            records.append(enriched)
    if len(records) != 2_700:
        raise RuntimeError(f"expected 2,700 records, found {len(records)}")
    return records


def _has_measurement(
    record: dict,
    quantities: set[str],
    predicate: Callable[[float], bool],
) -> bool:
    return any(
        measurement.quantity in quantities and predicate(measurement.value)
        for measurement in record["_measurements"]
    )


def _union_keyword_hits(
    variants: Iterable[str], records: list[dict]
) -> set[str]:
    return {
        study_id
        for variant in variants
        for study_id in keyword_baseline(variant, records)
    }


def _is_pediatric_brain(record: dict) -> bool:
    if record["BodyPartExamined"] != "BRAIN":
        return False
    return to_age_years(record["PatientAge"]) < 18.0


def _percent(value: object) -> str:
    if value is None:
        return "N/A"
    if not isinstance(value, float):
        raise TypeError("metric value must be a float or None")
    return f"{value * 100:.1f}%"


def main() -> None:
    print(render_results())


if __name__ == "__main__":
    main()
