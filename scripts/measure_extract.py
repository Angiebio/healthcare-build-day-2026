"""Deterministic extraction of quantitative facts from radiology prose."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Final, Literal


Laterality = Literal["left", "right", "bilateral"] | None
Qualifier = Literal["max", "mean"] | None

QUANTITY_VOCABULARY: Final[frozenset[str]] = frozenset(
    {
        "ejection_fraction",
        "left_ventricular_ejection_fraction",
        "right_ventricular_ejection_fraction",
        "gestational_age_weeks",
        "lateral_ventricular_atrial_width",
        "lesion_dimension",
        "chamber_volume",
        "regurgitant_fraction",
        "anatomic_dimension",
        "other_percentage",
    }
)

_NUMBER_WITH_UNIT = re.compile(
    r"(?<![\w.])(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>mm|cm|m[lL]|%|percent|weeks?|wks?)"
    r"(?![\w])",
    re.IGNORECASE,
)
_DIMENSION_PAIR = re.compile(
    r"(?<![\w.])(?P<first>\d+(?:\.\d+)?)\s*[x×]\s*"
    r"(?P<second>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm)(?![\w])",
    re.IGNORECASE,
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")
_NEGATION = re.compile(
    r"\b(?:no evidence of|without|absent|not seen|not identified|negative for)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Measurement:
    """A traceable numeric fact compiled from a source report."""

    quantity: str
    value: float
    unit: str
    raw_value: float
    raw_unit: str
    laterality: Laterality
    qualifier: Qualifier
    span: tuple[int, int]
    snippet: str
    confidence: float
    provenance: Literal["report_extraction"] = "report_extraction"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation without changing numeric precision."""

        return asdict(self)


def extract_measurements(report_text: str) -> list[Measurement]:
    """Compile typed measurements from a radiology report.

    Confidence is rule-derived: 0.99 for an explicit acronym or named quantity,
    0.96 for an explicit anatomic measurement phrase, 0.90 for a strong local
    context match, and 0.75 for a generic but unit-bearing dimension. Unit-bearing
    source text and exact character spans are mandatory, so every emitted number
    can be audited.

    Negation is handled conservatively: a value in a clause preceded by an
    explicit negator such as ``no evidence of`` is suppressed. This does not
    attempt full clinical assertion classification; uncertainty and historical
    findings remain out of scope for this four-hour deterministic compiler.
    """

    if not isinstance(report_text, str):
        raise TypeError("report_text must be a string")
    if not report_text.strip():
        return []

    measurements = _extract_dimension_pairs(report_text)
    dimension_spans = [match.span() for match in _DIMENSION_PAIR.finditer(report_text)]
    matches = list(_NUMBER_WITH_UNIT.finditer(report_text))
    sentence_spans = _sentence_spans(report_text)

    for match in matches:
        if any(start <= match.start() and match.end() <= end for start, end in dimension_spans):
            continue
        sentence_start, sentence_end = _containing_sentence(match.start(), sentence_spans)
        sentence = report_text[sentence_start:sentence_end]
        local_position = match.start() - sentence_start
        before = sentence[:local_position]
        after = sentence[match.end() - sentence_start :]

        if _is_negated(before):
            continue

        raw_value = float(match.group("value"))
        if not math.isfinite(raw_value):
            continue
        raw_unit = _canonical_raw_unit(match.group("unit"))
        quantity, confidence = _classify(
            sentence=sentence,
            local_position=local_position,
            raw_unit=raw_unit,
        )
        value, unit = _normalize(raw_value, raw_unit, quantity)
        laterality = _laterality(
            sentence=sentence,
            local_position=local_position,
        )
        qualifier = _qualifier(before[-48:], after[:32])
        snippet_start = max(0, match.start() - 48)
        snippet_end = min(len(report_text), match.end() + 48)

        measurements.append(
            Measurement(
                quantity=quantity,
                value=value,
                unit=unit,
                raw_value=raw_value,
                raw_unit=raw_unit,
                laterality=laterality,
                qualifier=qualifier,
                span=(match.start(), match.end()),
                snippet=report_text[snippet_start:snippet_end].strip(),
                confidence=confidence,
            )
        )

    return measurements


def _extract_dimension_pairs(report_text: str) -> list[Measurement]:
    measurements: list[Measurement] = []
    sentence_spans = _sentence_spans(report_text)
    for match in _DIMENSION_PAIR.finditer(report_text):
        sentence_start, sentence_end = _containing_sentence(match.start(), sentence_spans)
        sentence = report_text[sentence_start:sentence_end]
        local_position = match.start() - sentence_start
        before = sentence[:local_position]
        if _is_negated(before):
            continue

        raw_unit = _canonical_raw_unit(match.group("unit"))
        quantity, confidence = _classify(
            sentence=sentence,
            local_position=local_position,
            raw_unit=raw_unit,
        )
        laterality = _laterality(sentence=sentence, local_position=local_position)
        qualifier = _qualifier(before[-48:], sentence[match.end() - sentence_start :][:32])
        snippet_start = max(0, match.start() - 48)
        snippet_end = min(len(report_text), match.end() + 48)
        snippet = report_text[snippet_start:snippet_end].strip()

        for group_name in ("first", "second"):
            raw_value = float(match.group(group_name))
            value, unit = _normalize(raw_value, raw_unit, quantity)
            measurements.append(
                Measurement(
                    quantity=quantity,
                    value=value,
                    unit=unit,
                    raw_value=raw_value,
                    raw_unit=raw_unit,
                    laterality=laterality,
                    qualifier=qualifier,
                    span=match.span(group_name),
                    snippet=snippet,
                    confidence=confidence,
                )
            )
    return measurements


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for boundary in _SENTENCE_BOUNDARY.finditer(text):
        if boundary.start() > start:
            spans.append((start, boundary.start()))
        start = boundary.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans or [(0, len(text))]


def _containing_sentence(position: int, spans: list[tuple[int, int]]) -> tuple[int, int]:
    for start, end in spans:
        if start <= position <= end:
            return start, end
    raise ValueError(f"no sentence span contains source position {position}")


def _is_negated(before: str) -> bool:
    clause = re.split(r"[,;:]", before)[-1]
    return bool(_NEGATION.search(clause[-100:]))


def _canonical_raw_unit(unit: str) -> str:
    lowered = unit.lower()
    if lowered == "mm":
        return "mm"
    if lowered == "cm":
        return "cm"
    if lowered == "ml":
        return "mL"
    if lowered in {"%", "percent"}:
        return "%"
    if lowered in {"week", "weeks", "wk", "wks"}:
        return "weeks"
    raise ValueError(f"unsupported measurement unit: {unit!r}")


def _classify(*, sentence: str, local_position: int, raw_unit: str) -> tuple[str, float]:
    before = sentence[max(0, local_position - 140) : local_position].lower()
    after = sentence[local_position : local_position + 90].lower()
    context = before + " " + after

    if raw_unit == "weeks":
        if re.search(r"\b(?:gestation|gestational|fetal|fetus)\b", context):
            return "gestational_age_weeks", 0.99
        return "gestational_age_weeks", 0.90

    if raw_unit == "%":
        left_position = _last_context_position(
            before,
            ("lvef", "left ventricular ejection fraction", "left ventricular function"),
        )
        right_position = _last_context_position(
            before,
            ("rvef", "right ventricular ejection fraction", "right ventricular function"),
        )
        if left_position >= 0 and left_position > right_position:
            return "left_ventricular_ejection_fraction", 0.99
        if right_position >= 0 and right_position > left_position:
            return "right_ventricular_ejection_fraction", 0.99
        if "regurgitant fraction" in context:
            return "regurgitant_fraction", 0.99
        if "ejection fraction" in context or re.search(r"\bef\b", context):
            return "ejection_fraction", 0.96
        return "other_percentage", 0.75

    if raw_unit == "mL":
        if re.search(
            r"\b(?:end[- ]diastolic|end[- ]systolic|stroke|regurgitant|chamber|"
            r"ventricular|atrial|thoracic)\b.{0,55}\bvolume\b|\bvolume\b",
            context,
        ):
            return "chamber_volume", 0.96
        return "chamber_volume", 0.90

    if _is_atrial_width_context(context):
        return "lateral_ventricular_atrial_width", 0.96

    if re.search(
        r"\b(?:lesion|mass|nodule|cyst|defect|aneurysm|effusion|collection|"
        r"tumou?r|sac|herniation)\b",
        context,
    ):
        return "lesion_dimension", 0.90
    if re.search(r"\b(?:measur|diameter|dimension|width|thickness|length|displacement)\w*", context):
        return "anatomic_dimension", 0.90
    return "anatomic_dimension", 0.75


def _last_context_position(text: str, terms: tuple[str, ...]) -> int:
    return max((text.rfind(term) for term in terms), default=-1)


def _is_atrial_width_context(context: str) -> bool:
    atrial_language = re.search(
        r"\b(?:atrial|atria|atrium|ventricular atria|lateral ventricle)\b", context
    )
    width_language = re.search(
        r"\b(?:width|diameter|measur|dilat|caliber|ventriculomegaly)\w*", context
    )
    return bool(atrial_language and width_language)


def _normalize(
    raw_value: float, raw_unit: str, quantity: str
) -> tuple[float, str]:
    if raw_unit == "cm" and quantity in {
        "lateral_ventricular_atrial_width",
        "lesion_dimension",
        "anatomic_dimension",
    }:
        return raw_value * 10.0, "mm"
    return raw_value, raw_unit


def _laterality(
    *,
    sentence: str,
    local_position: int,
) -> Laterality:
    before = sentence[max(0, local_position - 100) : local_position].lower()
    after = sentence[local_position : local_position + 45].lower()

    after_side = re.search(r"\b(?:on|to)\s+the\s+(left|right)\b", after)
    if after_side:
        return after_side.group(1)  # type: ignore[return-value]
    if re.search(r"\bbilateral(?:ly)?\b|\bon both sides\b", before + " " + after):
        return "bilateral"

    last_left = before.rfind("left")
    last_right = before.rfind("right")
    if last_left >= 0 or last_right >= 0:
        if "left and right" in before[-100:] or "right and left" in before[-100:]:
            ordinal = sum(
                candidate.start() < local_position
                for candidate in _NUMBER_WITH_UNIT.finditer(sentence)
            )
            order = ("left", "right") if "left and right" in before[-100:] else ("right", "left")
            if ordinal < 2:
                return order[ordinal]  # type: ignore[return-value]
        return "left" if last_left > last_right else "right"
    return None


def _qualifier(before: str, after: str) -> Qualifier:
    context = (before + " " + after).lower()
    if re.search(r"\b(?:up to|max(?:imum|imal)?|largest)\b", context):
        return "max"
    if re.search(r"\b(?:mean|average)\b", context):
        return "mean"
    return None
