"""Validated query compiler: the executable boundary for Lantern searches."""

from __future__ import annotations

import math
import re
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .measure_extract import QUANTITY_VOCABULARY


class QueryError(ValueError):
    """Raised when a proposed query cannot be executed exactly as requested."""


PEDIATRIC_STAGES: Final[frozenset[str]] = frozenset(
    {"neonate", "infant", "early_childhood", "school_age", "adolescent", "adult"}
)
ALLOWED_CONCEPT_CODES: Final[frozenset[str]] = frozenset(
    {
        "SNOMED:12738006",  # Brain structure
        "SNOMED:80891009",  # Heart structure
        "SNOMED:241620005",  # Magnetic resonance imaging
        "SNOMED:276654001",  # Fetal structure
        "HPO:0002119",  # Ventriculomegaly
        "HPO:0000238",  # Hydrocephalus
        "HPO:0001631",  # Atrial septal defect
        "HPO:0001629",  # Ventricular septal defect
    }
)
_SUSPICIOUS_TEXT = re.compile(
    r"(?:ignore\s+(?:all\s+)?previous|system\s+prompt|developer\s+message|"
    r"<\s*script\b|drop\s+table|union\s+select|;\s*--|\bexec(?:ute)?\s*\()",
    re.IGNORECASE,
)

_QUANTITY_RULES: Final[dict[str, tuple[str, float, float]]] = {
    "ejection_fraction": ("%", 0.0, 100.0),
    "left_ventricular_ejection_fraction": ("%", 0.0, 100.0),
    "right_ventricular_ejection_fraction": ("%", 0.0, 100.0),
    "gestational_age_weeks": ("weeks", 0.0, 45.0),
    "lateral_ventricular_atrial_width": ("mm", 0.0, 100.0),
    "lesion_dimension": ("mm", 0.0, 2_000.0),
    "chamber_volume": ("mL", 0.0, 10_000.0),
    "regurgitant_fraction": ("%", 0.0, 100.0),
    "anatomic_dimension": ("mm", 0.0, 2_000.0),
    "other_percentage": ("%", 0.0, 100.0),
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PopulationQuery(_StrictModel):
    basis: Literal["chronological", "gestational"] = "chronological"
    stages: list[str] = Field(default_factory=list)
    age_min_years: float | None = None
    age_max_years: float | None = None
    gestational_age_min_weeks: float | None = None
    gestational_age_max_weeks: float | None = None
    sex: Literal["M", "F", "O", "unknown"] | None = None

    @field_validator("stages")
    @classmethod
    def validate_stages(cls, stages: list[str]) -> list[str]:
        unknown = set(stages) - PEDIATRIC_STAGES
        if unknown:
            raise ValueError(f"unknown population stage(s): {sorted(unknown)}")
        if len(stages) != len(set(stages)):
            raise ValueError("population stages must not contain duplicates")
        return stages

    @field_validator("age_min_years", "age_max_years")
    @classmethod
    def validate_age(cls, value: float | None) -> float | None:
        if value is None:
            return None
        _require_plain_number(value, "age")
        if not 0.0 <= value <= 130.0:
            raise ValueError("age must be between 0 and 130 years")
        return value

    @field_validator("gestational_age_min_weeks", "gestational_age_max_weeks")
    @classmethod
    def validate_gestational_age(cls, value: float | None) -> float | None:
        if value is None:
            return None
        _require_plain_number(value, "gestational age")
        if not 0.0 <= value <= 45.0:
            raise ValueError("gestational age must be between 0 and 45 weeks")
        return value

    @model_validator(mode="after")
    def validate_population_basis(self) -> "PopulationQuery":
        if (
            self.age_min_years is not None
            and self.age_max_years is not None
            and self.age_min_years > self.age_max_years
        ):
            raise ValueError("age_min_years cannot exceed age_max_years")
        if (
            self.gestational_age_min_weeks is not None
            and self.gestational_age_max_weeks is not None
            and self.gestational_age_min_weeks > self.gestational_age_max_weeks
        ):
            raise ValueError(
                "gestational_age_min_weeks cannot exceed gestational_age_max_weeks"
            )
        if self.basis == "gestational":
            if self.stages or self.age_min_years is not None or self.age_max_years is not None:
                raise ValueError(
                    "gestational populations cannot use chronological stages or age_years"
                )
        elif (
            self.gestational_age_min_weeks is not None
            or self.gestational_age_max_weeks is not None
        ):
            raise ValueError(
                "gestational age bounds require population.basis='gestational'"
            )
        return self


class ImagingQuery(_StrictModel):
    modality: list[Literal["MR", "CT", "US", "XR"]] = Field(default_factory=list)
    body_site: list[Literal["BRAIN", "HEART", "FETAL"]] = Field(default_factory=list)

    @field_validator("modality", "body_site")
    @classmethod
    def reject_duplicates(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("imaging filters must not contain duplicates")
        return values


class ClinicalQuery(_StrictModel):
    concepts: list[str] = Field(default_factory=list)
    text_terms: list[str] = Field(default_factory=list)
    expand_ontology: bool = False

    @field_validator("concepts")
    @classmethod
    def validate_concepts(cls, concepts: list[str]) -> list[str]:
        unknown = set(concepts) - ALLOWED_CONCEPT_CODES
        if unknown:
            raise ValueError(f"unknown clinical concept code(s): {sorted(unknown)}")
        return concepts

    @field_validator("text_terms")
    @classmethod
    def validate_text_terms(cls, terms: list[str]) -> list[str]:
        for term in terms:
            _validate_safe_text(term, "clinical text term", max_length=120)
        return terms


class NumericConstraint(_StrictModel):
    quantity: str
    op: Literal["lt", "lte", "gt", "gte", "between"]
    value: float | None = None
    range: list[float] | None = None
    unit: str

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, quantity: str) -> str:
        if quantity not in QUANTITY_VOCABULARY:
            raise ValueError(f"unknown numeric quantity: {quantity!r}")
        return quantity

    @model_validator(mode="after")
    def validate_constraint(self) -> "NumericConstraint":
        expected_unit, minimum, maximum = _QUANTITY_RULES[self.quantity]
        if self.unit != expected_unit:
            raise ValueError(
                f"{self.quantity} requires canonical unit {expected_unit!r}, got {self.unit!r}"
            )

        if self.op == "between":
            if self.value is not None or self.range is None:
                raise ValueError("between requires range=[low, high] and forbids value")
            if len(self.range) != 2:
                raise ValueError("between range must contain exactly [low, high]")
            low, high = self.range
            _validate_numeric_bound(low, minimum, maximum, self.quantity)
            _validate_numeric_bound(high, minimum, maximum, self.quantity)
            if low > high:
                raise ValueError("numeric range lower bound cannot exceed upper bound")
        else:
            if self.value is None or self.range is not None:
                raise ValueError(f"{self.op} requires value and forbids range")
            _validate_numeric_bound(self.value, minimum, maximum, self.quantity)
        return self


class AccessQuery(_StrictModel):
    min_layer: Literal["L0", "L1", "L2"] = "L1"


class QueryAST(_StrictModel):
    population: PopulationQuery = Field(default_factory=PopulationQuery)
    imaging: ImagingQuery = Field(default_factory=ImagingQuery)
    clinical: ClinicalQuery = Field(default_factory=ClinicalQuery)
    numeric: list[NumericConstraint] = Field(default_factory=list)
    access: AccessQuery = Field(default_factory=AccessQuery)

    @model_validator(mode="after")
    def validate_population_imaging_basis(self) -> "QueryAST":
        includes_fetal = "FETAL" in self.imaging.body_site
        if includes_fetal and self.population.basis != "gestational":
            raise ValueError(
                "FETAL imaging requires population.basis='gestational'; "
                "PatientAge is maternal age in this corpus"
            )
        if self.population.basis == "gestational" and self.imaging.body_site != ["FETAL"]:
            raise ValueError(
                "gestational population queries must target body_site=['FETAL']"
            )
        return self


def compile_query(nl_text: str | None, filters: dict[str, Any]) -> QueryAST:
    """Validate an exact executable query, rejecting rather than weakening it.

    Natural language is treated only as untrusted proposal context in this
    deterministic path. It is safety-checked but never interpreted or allowed to
    override ``filters``. An optional LLM adapter may construct filters upstream;
    only the resulting validated AST reaches a provider node.
    """

    if nl_text is not None:
        if not isinstance(nl_text, str):
            raise QueryError("nl_text must be a string or None")
        try:
            _validate_safe_text(nl_text, "natural-language query", max_length=1_000)
        except ValueError as exc:
            raise QueryError(f"query rejected: {exc}") from exc
    if not isinstance(filters, dict):
        raise QueryError("filters must be a dictionary")
    try:
        return QueryAST.model_validate(filters)
    except Exception as exc:
        raise QueryError(f"query rejected: {exc}") from exc


def _validate_safe_text(text: str, label: str, *, max_length: int) -> None:
    if not text.strip():
        raise ValueError(f"{label} must not be empty")
    if len(text) > max_length:
        raise ValueError(f"{label} exceeds {max_length} characters")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in text):
        raise ValueError(f"{label} contains control characters")
    if _SUSPICIOUS_TEXT.search(text):
        raise ValueError(f"{label} contains instruction or injection syntax")


def _require_plain_number(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a JSON number, not {type(value).__name__}")
    if not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")


def _validate_numeric_bound(
    value: float, minimum: float, maximum: float, quantity: str
) -> None:
    _require_plain_number(value, quantity)
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{quantity} value {value} outside allowed range [{minimum}, {maximum}]"
        )


GOLDEN_QUERY: Final[QueryAST] = compile_query(
    nl_text=None,
    filters={
        "population": {"basis": "gestational"},
        "imaging": {"modality": ["MR"], "body_site": ["FETAL"]},
        "numeric": [
            {
                "quantity": "lateral_ventricular_atrial_width",
                "op": "gt",
                "value": 10.0,
                "unit": "mm",
            }
        ],
        "access": {"min_layer": "L1"},
    },
)
