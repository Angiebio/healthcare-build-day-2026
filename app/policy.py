"""Server-side role -> release-layer redaction. Never client-trusted.

The UI role switcher is a *demo identity* with a banner; the server still decides
what each layer may see. Redaction is a projection, not a filter the client can
lift: a patient (L0) is handed plain-language codes and cohort existence, never
the measured values or the snippet that carries them. Fail-closed: an unknown role
collapses to the most restrictive layer.
"""
from __future__ import annotations

from typing import Any

ROLE_TO_LAYER: dict[str, str] = {"patient": "L0", "researcher": "L1", "clinician": "L2"}
# Nothing maps to L3, ever. L3 (source data) is petition-only, architecturally absent here.


def role_to_layer(role: str) -> str:
    return ROLE_TO_LAYER.get(role, "L0")  # unknown role -> most restrictive


def redact_for_layer(passport: dict[str, Any], layer: str) -> dict[str, Any]:
    """Project a passport down to what `layer` is permitted to see."""
    imaging = passport.get("imaging", {})
    population = passport.get("population", {})
    owner = passport.get("owner", {})

    if layer == "L0":
        # Public/patient: existence + plain-language shape only. No values, no snippets.
        return {
            "passport_id": passport.get("passport_id"),
            "owner": {"node": owner.get("node"), "label": owner.get("label")},
            "imaging": {
                "modality": imaging.get("modality"),
                "body_site": imaging.get("body_site", {}).get("display"),
            },
            "population": {
                "public_age_band": population.get("public_age_band"),
                "basis": population.get("basis"),
            },
            "has_quantitative_measurements": bool(passport.get("measurements")),
            "release_status": "PUBLIC_CATALOG_ONLY",
            "layer": "L0",
        }

    if layer == "L2":
        # Clinician: full researcher record + an explicit owner-contact route.
        out = dict(passport)
        out["layer"] = "L2"
        out["owner_contact_route"] = passport.get("owner", {}).get("request_route", "/petition")
        return out

    # L1 researcher (default): the full de-identified passport. No prose, no pixels.
    out = dict(passport)
    out["layer"] = "L1"
    return out
