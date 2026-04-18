"""FHIR R4 resource construction helpers.

We don't model every field of every resource — that's what the FHIR Python
SDK is for. These are minimal builders tuned for DaktariTB's needs:
just enough structure to produce valid resources a FHIR server will accept.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# --- LOINC codes we use ---
LOINC_GENEXPERT_MTB_RIF = "88142-3"
LOINC_AFB_SMEAR = "648-0"          # "Acid-fast bacilli stain"
LOINC_CHEST_XRAY = "36554-4"       # "Chest X-ray"
LOINC_LF_LAM = "95745-4"           # "MTB LAM Ag Xpert in urine"

# --- SNOMED codes ---
SNOMED_TUBERCULOSIS = "56717001"

# --- FHIR code systems ---
LOINC_SYSTEM = "http://loinc.org"
SNOMED_SYSTEM = "http://snomed.info/sct"


def now_iso() -> str:
    """Current UTC time as FHIR instant format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def codeable(system: str, code: str, display: str) -> dict[str, Any]:
    """Build a FHIR CodeableConcept."""
    return {
        "coding": [{"system": system, "code": code, "display": display}],
        "text": display,
    }


def service_request(
    *,
    patient_id: str,
    code_system: str,
    code: str,
    display: str,
    category_code: str = "laboratory",
    category_display: str = "Laboratory procedure",
    priority: str = "routine",
    reason_references: list[str] | None = None,
    reason_text: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR ServiceRequest (a lab or imaging order).

    Args:
        patient_id: FHIR id of the patient (e.g., "193068e4-...")
        code_system: URL of the coding system (LOINC usually)
        code: the code value (e.g., "88142-3" for GeneXpert)
        display: human-readable name
        category_code: "laboratory" or "imaging"
        priority: "routine", "urgent", "asap", or "stat"
        reason_references: list of "Condition/xxx" or "Observation/xxx" refs
        reason_text: free-text clinical reason if no references fit
    """
    resource: dict[str, Any] = {
        "resourceType": "ServiceRequest",
        "status": "active",
        "intent": "order",
        "priority": priority,
        "category": [
            codeable(
                "http://terminology.hl7.org/CodeSystem/service-category",
                category_code,
                category_display,
            )
        ],
        "code": codeable(code_system, code, display),
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": now_iso(),
        "requester": {
            "display": "DaktariTB MCP Agent",
        },
    }

    if reason_references:
        resource["reasonReference"] = [{"reference": ref} for ref in reason_references]
    if reason_text:
        resource["reasonCode"] = [{"text": reason_text}]

    return resource
