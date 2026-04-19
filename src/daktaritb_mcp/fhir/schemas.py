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


# --- RxNorm codes (US-centric but widely used in FHIR) ---
# Dolutegravir 50 mg oral tablet
RXNORM_DTG_50MG = "1747694"
# TLD fixed-dose combination (Tenofovir/Lamivudine/Dolutegravir)
RXNORM_TLD = "2180325"
# Rifampicin
RXNORM_RIFAMPICIN = "9384"

# --- SNOMED clinical codes for interactions ---
SNOMED_DDI_SERIOUS = "282100009"  # "Adverse reaction caused by drug"
SNOMED_DDI_INTERACTION = "182842008"  # "Drug interaction"


def medication_request(
    *,
    patient_id: str,
    medication_code: str,
    medication_display: str,
    dose_quantity_value: float,
    dose_unit: str,
    dose_unit_code: str,
    dose_frequency: int,
    dose_period: float,
    dose_period_unit: str,
    route_code: str = "26643006",  # SNOMED: Oral
    route_display: str = "Oral route",
    status: str = "active",
    intent: str = "order",
    priority: str = "routine",
    reason_references: list[str] | None = None,
    reason_text: str | None = None,
    supersedes: str | None = None,
    detected_issue: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR MedicationRequest (a prescription order).

    Args:
        patient_id: FHIR id of the patient
        medication_code: RxNorm or ATC code
        medication_display: human-readable drug name
        dose_quantity_value: amount per dose (e.g., 50)
        dose_unit: display unit (e.g., "mg")
        dose_unit_code: UCUM code (e.g., "mg")
        dose_frequency: number of doses per period (e.g., 2 for BID)
        dose_period: length of period (e.g., 1)
        dose_period_unit: UCUM period unit (e.g., "d" for day)
        supersedes: optional "MedicationRequest/<id>" ref to the old prescription
        detected_issue: optional "DetectedIssue/<id>" ref documenting why changed
        note: free-text note added to the prescription
    """
    resource: dict[str, Any] = {
        "resourceType": "MedicationRequest",
        "status": status,
        "intent": intent,
        "priority": priority,
        "medicationCodeableConcept": codeable(
            "http://www.nlm.nih.gov/research/umls/rxnorm",
            medication_code,
            medication_display,
        ),
        "subject": {"reference": f"Patient/{patient_id}"},
        "authoredOn": now_iso(),
        "requester": {"display": "DaktariTB MCP Agent"},
        "dosageInstruction": [
            {
                "text": f"{medication_display} {dose_quantity_value} {dose_unit} "
                + (
                    "twice daily"
                    if dose_frequency == 2 and dose_period == 1 and dose_period_unit == "d"
                    else "once daily"
                    if dose_frequency == 1 and dose_period == 1 and dose_period_unit == "d"
                    else f"{dose_frequency} times per {dose_period}{dose_period_unit}"
                ),
                "timing": {
                    "repeat": {
                        "frequency": dose_frequency,
                        "period": dose_period,
                        "periodUnit": dose_period_unit,
                    }
                },
                "route": codeable(SNOMED_SYSTEM, route_code, route_display),
                "doseAndRate": [
                    {
                        "doseQuantity": {
                            "value": dose_quantity_value,
                            "unit": dose_unit,
                            "system": "http://unitsofmeasure.org",
                            "code": dose_unit_code,
                        }
                    }
                ],
            }
        ],
    }

    if reason_references:
        resource["reasonReference"] = [{"reference": ref} for ref in reason_references]
    if reason_text:
        resource["reasonCode"] = [{"text": reason_text}]
    if supersedes:
        resource["priorPrescription"] = {"reference": supersedes}
    if detected_issue:
        resource["detectedIssue"] = [{"reference": detected_issue}]
    if note:
        resource["note"] = [{"text": note}]

    return resource


def detected_issue(
    *,
    patient_id: str,
    severity: str,
    issue_code: str,
    issue_display: str,
    detail: str,
    implicated_references: list[str] | None = None,
    evidence_detail: str | None = None,
    mitigation: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR DetectedIssue resource.

    A DetectedIssue formally documents a clinical concern identified about the
    patient's chart — drug-drug interactions, duplicate therapies, contraindications.
    It's the FHIR-native way to record "something requires attention here."

    Args:
        severity: "high", "moderate", or "low"
        issue_code: SNOMED code for the issue type
        issue_display: human-readable issue name
        detail: text explanation of the issue
        implicated_references: list of resource refs that are involved
            (e.g., the original MedicationStatement + the new rifampicin order)
        evidence_detail: source of the evidence (e.g., WHO guideline citation)
        mitigation: what action was taken to address the issue
    """
    if severity not in ("high", "moderate", "low"):
        raise ValueError(f"Invalid severity '{severity}'. Must be high/moderate/low.")

    resource: dict[str, Any] = {
        "resourceType": "DetectedIssue",
        "status": "final",
        "severity": severity,
        "code": codeable(SNOMED_SYSTEM, issue_code, issue_display),
        "patient": {"reference": f"Patient/{patient_id}"},
        "identifiedDateTime": now_iso(),
        "author": {"display": "DaktariTB MCP Agent"},
        "detail": detail,
    }

    if implicated_references:
        resource["implicated"] = [{"reference": ref} for ref in implicated_references]

    if evidence_detail:
        resource["evidence"] = [
            {
                "detail": [{"display": evidence_detail}],
            }
        ]

    if mitigation:
        resource["mitigation"] = [
            {
                "action": codeable(SNOMED_SYSTEM, "281647001", "Adverse reaction mitigation"),
                "date": now_iso(),
                "author": {"display": "DaktariTB MCP Agent"},
            }
        ]

    return resource


# --- DocumentReference codes (LOINC) ---
LOINC_TB_CASE_REPORT = "67796-1"   # "Public Health Case Report - US National Notifiable Condition Mapping"
# Generic "Patient transfer note" fallback when a more specific code isn't appropriate.


def document_reference(
    *,
    patient_id: str,
    pdf_base64: str,
    title: str,
    description: str,
    document_type_code: str = LOINC_TB_CASE_REPORT,
    document_type_display: str = "Public health case report",
    category_code: str = "health-summary",
    category_display: str = "Health summary",
    related_conditions: list[str] | None = None,
    facility_name: str | None = None,
    notification_date: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR DocumentReference wrapping a base64-encoded PDF.

    Args:
        patient_id: FHIR id of the patient
        pdf_base64: base64-encoded PDF bytes (contentType application/pdf)
        title: human-readable document title
        description: short description of the document
        document_type_code: LOINC code for the document
        category_code: DocumentReferenceCategory code
        related_conditions: list of "Condition/<id>" refs the document relates to
        facility_name: facility that produced the document
        notification_date: ISO date of the notification (defaults to now)
    """
    resource: dict[str, Any] = {
        "resourceType": "DocumentReference",
        "status": "current",
        "docStatus": "final",
        "type": codeable(LOINC_SYSTEM, document_type_code, document_type_display),
        "category": [
            codeable(
                "http://hl7.org/fhir/us/core/CodeSystem/us-core-documentreference-category",
                category_code,
                category_display,
            )
        ],
        "subject": {"reference": f"Patient/{patient_id}"},
        "date": notification_date or now_iso(),
        "author": [{"display": "DaktariTB MCP Agent"}],
        "description": description,
        "content": [
            {
                "attachment": {
                    "contentType": "application/pdf",
                    "data": pdf_base64,
                    "title": title,
                    "creation": notification_date or now_iso(),
                }
            }
        ],
    }

    if related_conditions:
        resource["context"] = {
            "related": [{"reference": ref} for ref in related_conditions]
        }

    if facility_name:
        # FHIR custodian would usually be a real Organization reference; for
        # the demo we use the display slot only.
        resource["custodian"] = {"display": facility_name}

    return resource
