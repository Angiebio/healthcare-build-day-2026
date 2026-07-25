"""Small, corpus-grounded terminology service for Lantern.

The public boundary is deliberately production-shaped: replacing
``CuratedTerminology`` with a client backed by a licensed terminology server is
one class swap.  We do not bundle SNOMED CT content.  Today's implementation is
a small hand-curated graph derived from the 2,700 synthetic challenge reports.

Only codes already admitted by Lantern's validated query AST are emitted.  Their
canonical identifier sources are recorded in ``CURATED_CODE_SOURCES``.  Terms
whose identifiers were not verified are kept explicitly uncoded; a visible gap
is safer than a fabricated clinical code.

This module is pure: no file, network, environment, clock, or process access.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from .query_ast import ALLOWED_CONCEPT_CODES, QueryAST

System = Literal["SCT", "HPO", "ORPHA"]
Relationship = Literal["exact", "synonym", "ancestor", "descendant", "related"]
Provenance = Literal["curated", "uncoded"]


class Concept(BaseModel):
    """A terminology match, honest about both relationship and coding status."""

    model_config = ConfigDict(frozen=True)

    system: System | None = None
    code: str | None = None
    display: str
    relationship: Relationship
    provenance: Provenance


class ExpansionTrace(BaseModel):
    """Why an input concept gained a query alternative."""

    model_config = ConfigDict(frozen=True)

    source: str
    expanded_to: str
    relationship: Relationship
    system: System | None = None
    code: str | None = None
    provenance: Provenance


class ExpandedQueryAST(QueryAST):
    """A validated Query AST plus auditable ontology-expansion evidence."""

    ontology_expansion: list[ExpansionTrace] = Field(default_factory=list)


@runtime_checkable
class TerminologyService(Protocol):
    """Swap boundary for a curated graph or a production terminology server."""

    def lookup(self, term: str) -> list[Concept]:
        """Map a surface term to exact and semantically connected concepts."""

    def expand(self, code: str, *, direction: str = "both") -> list[Concept]:
        """Expand a coded concept along the requested graph direction."""

    def synonyms(self, term: str) -> list[str]:
        """Return corpus-facing synonyms for a surface term."""


@dataclass(frozen=True)
class _Definition:
    key: str
    display: str
    aliases: tuple[str, ...] = ()
    system: System | None = None
    code: str | None = None


@dataclass(frozen=True)
class _Cluster:
    root: str
    # Relationships are stated from the root concept to each member.
    members: tuple[tuple[str, Relationship], ...]


# Canonical identifier URIs are citations, not bundled terminology content.
CURATED_CODE_SOURCES: Final[dict[str, str]] = {
    "SNOMED:12738006": "http://snomed.info/id/12738006",
    "SNOMED:80891009": "http://snomed.info/id/80891009",
    "SNOMED:241620005": "http://snomed.info/id/241620005",
    "SNOMED:276654001": "http://snomed.info/id/276654001",
    "HPO:0002119": "https://hpo.jax.org/app/browse/term/HP:0002119",
    "HPO:0000238": "https://hpo.jax.org/app/browse/term/HP:0000238",
    "HPO:0001631": "https://hpo.jax.org/app/browse/term/HP:0001631",
    "HPO:0001629": "https://hpo.jax.org/app/browse/term/HP:0001629",
}


_DEFINITIONS: Final[dict[str, _Definition]] = {
    # Challenge-literal semantic bridge.
    "tumor": _Definition("tumor", "tumor"),
    "neoplasm": _Definition("neoplasm", "neoplasm"),
    "glioma": _Definition("glioma", "glioma"),
    "low_grade_glioma": _Definition(
        "low_grade_glioma", "low-grade glioma", ("low grade glioma",)
    ),
    "astrocytoma": _Definition("astrocytoma", "astrocytoma"),
    "mass": _Definition("mass", "mass"),
    "lesion": _Definition("lesion", "lesion"),
    # Hero-query condition. Both UK and US spelling occur in the reports.
    "ventriculomegaly": _Definition(
        "ventriculomegaly",
        "ventriculomegaly",
        system="HPO",
        code="HPO:0002119",
    ),
    "ventricular_dilatation": _Definition(
        "ventricular_dilatation", "ventricular dilatation"
    ),
    "ventricular_dilation": _Definition(
        "ventricular_dilation", "ventricular dilation"
    ),
    "hydrocephalus": _Definition(
        "hydrocephalus", "hydrocephalus", system="HPO", code="HPO:0000238"
    ),
    "enlarged_lateral_ventricles": _Definition(
        "enlarged_lateral_ventricles", "enlarged lateral ventricles"
    ),
    "atrial_width": _Definition(
        "atrial_width",
        "lateral ventricular atrial width",
        ("atrial width", "atrial widths", "ventricular atrium"),
    ),
    "dilated_lateral_ventricle": _Definition(
        "dilated_lateral_ventricle",
        "dilated lateral ventricle",
        ("dilated ventricle",),
    ),
    # Anatomy represented in all three nodes.
    "brain": _Definition(
        "brain", "brain", system="SCT", code="SNOMED:12738006"
    ),
    "cerebral_structure": _Definition(
        "cerebral_structure", "cerebral structure", ("cerebral",)
    ),
    "lateral_ventricle": _Definition("lateral_ventricle", "lateral ventricle"),
    "corpus_callosum": _Definition("corpus_callosum", "corpus callosum"),
    "heart": _Definition(
        "heart", "heart", ("cardiac",), system="SCT", code="SNOMED:80891009"
    ),
    "cardiac_chamber": _Definition("cardiac_chamber", "cardiac chamber"),
    "myocardium": _Definition("myocardium", "myocardium", ("myocardial",)),
    "cardiac_ventricle": _Definition(
        "cardiac_ventricle", "cardiac ventricle", ("left ventricle", "right ventricle")
    ),
    "fetal_structure": _Definition(
        "fetal_structure",
        "fetal structure",
        ("fetal",),
        system="SCT",
        code="SNOMED:276654001",
    ),
    "fetus": _Definition("fetus", "fetus"),
    # Cardiac function cluster behind the EF < 40% demo opener.
    "cardiomyopathy": _Definition("cardiomyopathy", "cardiomyopathy"),
    "dilated_cardiomyopathy": _Definition(
        "dilated_cardiomyopathy", "dilated cardiomyopathy"
    ),
    "ejection_fraction": _Definition("ejection_fraction", "ejection fraction"),
    "reduced_ejection_fraction": _Definition(
        "reduced_ejection_fraction",
        "reduced ejection fraction",
        ("depressed ejection fraction",),
    ),
    "systolic_dysfunction": _Definition(
        "systolic_dysfunction", "systolic dysfunction"
    ),
    "myocardial_disease": _Definition(
        "myocardial_disease", "myocardial disease", ("myocardial",)
    ),
    # Cerebrovascular language differs conspicuously across the reports.
    "infarct": _Definition("infarct", "infarct"),
    "infarction": _Definition("infarction", "infarction"),
    "ischemic_injury": _Definition(
        "ischemic_injury", "ischemic injury", ("ischemic",)
    ),
    "ischemia": _Definition("ischemia", "ischemia"),
    "stroke": _Definition("stroke", "stroke"),
    # Genuine HPO-coded findings in the cardiac corpus.
    "septal_defect": _Definition("septal_defect", "septal defect"),
    "atrial_septal_defect": _Definition(
        "atrial_septal_defect",
        "atrial septal defect",
        ("asd",),
        system="HPO",
        code="HPO:0001631",
    ),
    "ventricular_septal_defect": _Definition(
        "ventricular_septal_defect",
        "ventricular septal defect",
        ("vsd",),
        system="HPO",
        code="HPO:0001629",
    ),
}


_CLUSTERS: Final[tuple[_Cluster, ...]] = (
    _Cluster(
        "tumor",
        (
            ("tumor", "exact"),
            ("neoplasm", "synonym"),
            ("glioma", "descendant"),
            ("low_grade_glioma", "descendant"),
            ("astrocytoma", "descendant"),
            ("mass", "related"),
            ("lesion", "related"),
        ),
    ),
    _Cluster(
        "ventriculomegaly",
        (
            ("ventriculomegaly", "exact"),
            ("ventricular_dilatation", "synonym"),
            ("ventricular_dilation", "synonym"),
            ("hydrocephalus", "related"),
            ("enlarged_lateral_ventricles", "synonym"),
            ("atrial_width", "related"),
            ("dilated_lateral_ventricle", "synonym"),
        ),
    ),
    _Cluster(
        "brain",
        (
            ("brain", "exact"),
            ("cerebral_structure", "synonym"),
            ("lateral_ventricle", "descendant"),
            ("corpus_callosum", "descendant"),
        ),
    ),
    _Cluster(
        "heart",
        (
            ("heart", "exact"),
            ("cardiac_chamber", "descendant"),
            ("myocardium", "descendant"),
            ("cardiac_ventricle", "descendant"),
        ),
    ),
    _Cluster(
        "fetal_structure",
        (("fetal_structure", "exact"), ("fetus", "synonym")),
    ),
    _Cluster(
        "cardiomyopathy",
        (
            ("cardiomyopathy", "exact"),
            ("dilated_cardiomyopathy", "descendant"),
            ("ejection_fraction", "related"),
            ("reduced_ejection_fraction", "related"),
            ("systolic_dysfunction", "related"),
            ("myocardial_disease", "ancestor"),
        ),
    ),
    _Cluster(
        "infarct",
        (
            ("infarct", "exact"),
            ("infarction", "synonym"),
            ("ischemic_injury", "synonym"),
            ("ischemia", "related"),
            ("stroke", "related"),
        ),
    ),
    _Cluster(
        "septal_defect",
        (
            ("septal_defect", "exact"),
            ("atrial_septal_defect", "descendant"),
            ("ventricular_septal_defect", "descendant"),
        ),
    ),
)

CURATED_SURFACE_TERMS: Final[tuple[str, ...]] = tuple(
    sorted(
        {
            surface
            for definition in _DEFINITIONS.values()
            for surface in (definition.display, *definition.aliases)
        }
    )
)

_CODE_INDEX: Final[dict[str, str]] = {
    definition.code: definition.key
    for definition in _DEFINITIONS.values()
    if definition.code is not None
}


class CuratedTerminology(TerminologyService):
    """Corpus-specific graph used today; production servers implement the same Protocol."""

    def lookup(self, term: str) -> list[Concept]:
        normalized = _normalize(term)
        if not normalized:
            return []

        matches: list[Concept] = []
        seen: set[tuple[str, Relationship]] = set()
        for cluster in _CLUSTERS:
            anchor_keys = [
                key
                for key, _ in cluster.members
                if _definition_occurs(_DEFINITIONS[key], normalized)
            ]
            if not anchor_keys:
                continue

            # A free-text phrase may mention anatomy and a condition together
            # ("pediatric brain tumor"). Flattening both clusters into one OR-list
            # would turn that into "brain OR tumor" and flood the cohort. Cluster
            # order therefore encodes deliberate clinical specificity: the first
            # recognized condition wins; anatomy still resolves when queried alone.
            anchor_key = cluster.root if cluster.root in anchor_keys else anchor_keys[0]
            for target_key, _ in cluster.members:
                relationship = _relationship(cluster, anchor_key, target_key)
                marker = (target_key, relationship)
                if marker in seen:
                    continue
                seen.add(marker)
                matches.append(_as_concept(_DEFINITIONS[target_key], relationship))
            return matches
        return []

    def expand(self, code: str, *, direction: str = "both") -> list[Concept]:
        normalized_direction = _normalize_direction(direction)
        canonical_code = _canonical_code(code)
        anchor_key = _CODE_INDEX.get(canonical_code)
        if anchor_key is None:
            return []

        matches: list[Concept] = []
        seen: set[tuple[str, Relationship]] = set()
        for cluster in _CLUSTERS:
            if anchor_key not in {key for key, _ in cluster.members}:
                continue
            for target_key, _ in cluster.members:
                relationship = _relationship(cluster, anchor_key, target_key)
                if not _direction_allows(normalized_direction, relationship):
                    continue
                marker = (target_key, relationship)
                if marker in seen:
                    continue
                seen.add(marker)
                matches.append(_as_concept(_DEFINITIONS[target_key], relationship))
        return matches

    def synonyms(self, term: str) -> list[str]:
        return _deduplicate(
            concept.display
            for concept in self.lookup(term)
            if concept.relationship == "synonym"
        )


def expand_query_concepts(
    ast: QueryAST, service: TerminologyService
) -> ExpandedQueryAST:
    """Return a newly validated AST with OR-alternatives and expansion evidence.

    The clinical ``text_terms`` added here are semantic alternatives, not
    cumulative AND predicates.  Node retrieval should match any alternative and
    use ``ontology_expansion`` to explain which bridge fired.
    """

    if not isinstance(ast, QueryAST):
        raise TypeError("ast must be a validated QueryAST")
    if not isinstance(service, TerminologyService):
        raise TypeError("service must implement TerminologyService")

    payload = ast.model_dump()
    clinical = payload["clinical"]
    if not clinical["expand_ontology"]:
        return ExpandedQueryAST.model_validate(payload)

    text_terms: list[str] = list(clinical["text_terms"])
    concept_codes: list[str] = list(clinical["concepts"])
    traces: list[ExpansionTrace] = []
    trace_keys: set[tuple[str, str, Relationship]] = set()

    for source in tuple(text_terms):
        _merge_expansion(
            source,
            service.lookup(source),
            text_terms,
            concept_codes,
            traces,
            trace_keys,
        )

    for source in tuple(concept_codes):
        _merge_expansion(
            source,
            service.expand(source),
            text_terms,
            concept_codes,
            traces,
            trace_keys,
        )

    clinical["text_terms"] = _deduplicate(text_terms)
    clinical["concepts"] = _deduplicate(concept_codes)
    payload["ontology_expansion"] = [trace.model_dump() for trace in traces]
    return ExpandedQueryAST.model_validate(payload)


def _merge_expansion(
    source: str,
    concepts: list[Concept],
    text_terms: list[str],
    concept_codes: list[str],
    traces: list[ExpansionTrace],
    trace_keys: set[tuple[str, str, Relationship]],
) -> None:
    for concept in concepts:
        if concept.relationship != "exact":
            text_terms.append(concept.display)
        if concept.code is not None:
            if concept.code not in ALLOWED_CONCEPT_CODES:
                raise ValueError(
                    f"terminology service emitted code outside the validated AST: {concept.code}"
                )
            concept_codes.append(concept.code)
        if concept.relationship == "exact":
            continue
        trace_key = (source, concept.display, concept.relationship)
        if trace_key in trace_keys:
            continue
        trace_keys.add(trace_key)
        traces.append(
            ExpansionTrace(
                source=source,
                expanded_to=concept.display,
                relationship=concept.relationship,
                system=concept.system,
                code=concept.code,
                provenance=concept.provenance,
            )
        )


def _relationship(
    cluster: _Cluster, anchor_key: str, target_key: str
) -> Relationship:
    if anchor_key == target_key:
        return "exact"
    root_relationships = dict(cluster.members)
    anchor_relationship = root_relationships[anchor_key]
    target_relationship = root_relationships[target_key]
    if anchor_key == cluster.root:
        return target_relationship
    if target_key == cluster.root:
        return _inverse(anchor_relationship)
    if anchor_relationship == "synonym":
        return target_relationship
    if target_relationship == "synonym":
        return _inverse(anchor_relationship)
    return "related"


def _inverse(relationship: Relationship) -> Relationship:
    if relationship == "ancestor":
        return "descendant"
    if relationship == "descendant":
        return "ancestor"
    return relationship


def _as_concept(definition: _Definition, relationship: Relationship) -> Concept:
    return Concept(
        system=definition.system,
        code=definition.code,
        display=definition.display,
        relationship=relationship,
        provenance="curated" if definition.code is not None else "uncoded",
    )


def _definition_occurs(definition: _Definition, normalized_input: str) -> bool:
    return any(
        _surface_occurs(_normalize(surface), normalized_input)
        for surface in (definition.display, *definition.aliases)
    )


def _surface_occurs(surface: str, normalized_input: str) -> bool:
    if not surface:
        return False
    return re.search(
        rf"(?<![a-z0-9]){re.escape(surface)}(?![a-z0-9])", normalized_input
    ) is not None


def _normalize(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(re.sub(r"[-_/]+", " ", value.casefold()).split())


def _canonical_code(code: str) -> str:
    if not isinstance(code, str):
        return ""
    value = code.strip().upper()
    if value.startswith("SCT:"):
        return f"SNOMED:{value.removeprefix('SCT:')}"
    return value


def _normalize_direction(direction: str) -> Literal["both", "ancestors", "descendants"]:
    if not isinstance(direction, str):
        raise ValueError("direction must be 'both', 'ancestors', or 'descendants'")
    normalized = direction.casefold()
    aliases = {
        "both": "both",
        "ancestor": "ancestors",
        "ancestors": "ancestors",
        "descendant": "descendants",
        "descendants": "descendants",
    }
    if normalized not in aliases:
        raise ValueError("direction must be 'both', 'ancestors', or 'descendants'")
    return cast(
        Literal["both", "ancestors", "descendants"], aliases[normalized]
    )


def _direction_allows(
    direction: Literal["both", "ancestors", "descendants"],
    relationship: Relationship,
) -> bool:
    if direction == "both":
        return True
    if direction == "ancestors":
        return relationship in {"exact", "synonym", "ancestor"}
    return relationship in {"exact", "synonym", "descendant"}


def _deduplicate(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        marker = value.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        output.append(value)
    return output
