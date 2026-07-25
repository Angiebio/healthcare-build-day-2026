"""Study Passport — the only representation permitted to leave a hospital node.

Technical: typed models for the compiled, de-identified study representation.
Philosophical: this file defines the shape of a promise. Everything a hospital
is willing to say about a patient, and nothing it isn't. The fields that are
absent here are as load-bearing as the fields that are present -- there is no
`report_text`, no `patient_name`, no pixel reference, because a structure that
cannot carry a thing cannot leak it.

Design rule enforced here: every clinical fact carries its own provenance and,
where a machine produced it, a confidence and the source snippet. A model's
guess must never be indistinguishable from a radiologist's measurement.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Where a fact came from. This vocabulary is closed on purpose: an unlabelled
# fact is not permitted to exist.
Provenance = Literal[
    "native_field",       # read directly from a structured source field
    "report_extraction",  # parsed out of clinical prose by our extractor
    "curated",            # from a human-maintained mapping table
    "derived",            # computed from other passport fields
]

# What we are willing to release, and to whom. Ordered least to most permissive.
ReleaseStatus = Literal[
    "BLOCKED",
    "HUMAN_REVIEW_REQUIRED",
    "PUBLIC_CATALOG_ONLY",
    "CONTROLLED_DERIVATIVE",
    "APPROVED_DEIDENTIFIED",
    "OWNER_AUTHORIZED_SOURCE_ACCESS",
]

ReleaseLayer = Literal["L0", "L1", "L2"]  # L3 (source data) is never served.


class CodedConcept(BaseModel):
    """A clinical concept in a standard vocabulary.

    `code` is Optional by design. An uncoded concept with an honest display term
    is worth more than a fabricated identifier -- in this domain a wrong SNOMED
    code is a worse failure than a missing one.
    """

    system: Optional[str] = None           # "SCT" | "HPO" | "ORPHA" | None
    code: Optional[str] = None
    display: str
    provenance: Provenance = "curated"
    confidence: Optional[float] = None
    relationship: Optional[str] = None     # exact | synonym | ancestor | descendant


class MeasurementFact(BaseModel):
    """A quantitative clinical value lifted out of prose and made computable.

    This is the reason Lantern exists. The number was always in the record; it
    was simply written in a form no search could reach and no privacy office
    could safely release.
    """

    quantity: str                          # from the extractor's closed vocabulary
    value: float
    unit: str
    laterality: Optional[str] = None
    qualifier: Optional[str] = None
    confidence: float
    snippet: str                           # the phrase it came from, for human audit
    provenance: Provenance = "report_extraction"


class Population(BaseModel):
    """Age representation, generalized -- and honest about what kind of age it is.

    `basis` exists because of a real trap in this corpus: on fetal studies the
    recorded patient age is the *mother's*. Running pediatric banding over it
    would label a fetus an adult. A fetal-medicine clinician would spot that in
    one second, and rightly stop trusting everything else on the page.
    """

    basis: Literal["chronological", "gestational", "unknown"] = "chronological"
    pediatric_stage: Optional[str] = None      # chronological only
    public_age_band: Optional[str] = None      # chronological only
    gestational_age_weeks: Optional[float] = None
    sex: Optional[str] = None


class Imaging(BaseModel):
    modality: str
    body_part_raw: str
    body_site: Optional[CodedConcept] = None


class ComputationalReadiness(BaseModel):
    """What analysis this study can actually support.

    `missing_for_full_computability` is the most credible field in the system.
    A researcher deciding whether to spend six months on a cohort is far better
    served by an honest inventory than an impressive one -- and naming the gap
    is what separates a research instrument from a demo.
    """

    has_quantitative_measurements: bool = False
    measurement_count: int = 0
    quantities_available: list[str] = Field(default_factory=list)
    supports_quantitative_cohort_analysis: bool = False
    supports_threshold_stratification: bool = False
    missing_for_full_computability: list[str] = Field(default_factory=list)


class DeidManifest(BaseModel):
    """Evidence of the transformation, travelling with the data.

    A privacy claim that cannot be audited is not a privacy claim. The receiving
    institution should not have to trust our description of what we removed;
    they should be able to read it.
    """

    removed: list[str] = Field(default_factory=list)
    generalized: list[str] = Field(default_factory=list)
    pseudonymized: list[str] = Field(default_factory=list)
    prose_withheld: bool = True
    pixel_data_present: bool = False
    profile: str = "DICOM PS3.15-aligned (Basic Application Level Confidentiality Profile)"
    notes: list[str] = Field(default_factory=list)


class Privacy(BaseModel):
    highest_release_layer: ReleaseLayer = "L1"
    release_status: ReleaseStatus = "CONTROLLED_DERIVATIVE"
    patient_identity_removed: bool = True
    free_text_released: bool = False


class Owner(BaseModel):
    node: str
    display_name: str
    request_route: str = "/petition"


class Passport(BaseModel):
    """The compiled study. This crosses the trust boundary; nothing else does."""

    passport_id: str
    owner: Owner
    imaging: Imaging
    population: Population
    measurements: list[MeasurementFact] = Field(default_factory=list)
    concepts: list[CodedConcept] = Field(default_factory=list)
    computational_readiness: ComputationalReadiness
    privacy: Privacy
    deid_manifest: DeidManifest
    provenance: dict[str, Any] = Field(default_factory=dict)

    def public_view(self) -> dict[str, Any]:
        """L0: what an unauthenticated member of the public may see.

        Deliberately coarse. Coded findings and a broad age band tell a patient
        whether their condition is represented in research without telling
        anyone which record is theirs.
        """
        return {
            "passport_id": self.passport_id,
            "owner": self.owner.display_name,
            "modality": self.imaging.modality,
            "body_part": self.imaging.body_part_raw,
            "concepts": [c.display for c in self.concepts],
            "age_band": self.population.public_age_band,
            "release_layer": "L0",
        }
