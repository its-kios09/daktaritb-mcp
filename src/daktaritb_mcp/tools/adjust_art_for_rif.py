"""adjust_art_for_rif — handle the DTG-rifampicin interaction.

INTENT
  When a PLHIV patient on dolutegravir-based ART (TLD = Tenofovir /
  Lamivudine / Dolutegravir) is on rifampicin (first-line TB treatment),
  rifampicin induces UGT1A1 and lowers DTG levels to sub-therapeutic.
  Standard of care: double-dose DTG (50 mg BID) for the duration of
  rifampicin therapy plus 2 weeks after.

  This tool:
    1. Fetches current medications + conditions
    2. Verifies the patient is HIV+ and on DTG-based ART
    3. Verifies rifampicin is prescribed (or about to be — caller confirms)
    4. Creates a DetectedIssue documenting the UGT1A1 interaction
    5. Creates a new MedicationRequest for DTG 50mg BID, linked to the
       DetectedIssue and marking the original as superseded

CLINICAL REFERENCE
  WHO Consolidated Guidelines on the Use of Antiretroviral Drugs for
  Treating and Preventing HIV Infection (2021), sections on TB/HIV
  co-administration.

INPUTS
  Optional:
    confirm_rifampicin_present: bool (default: tool auto-detects)
      If True, skips the check for rifampicin in the chart. Used when
      rifampicin is about to be started (not yet in chart).
    continuation_weeks_post_rif: int (default: 2)
      How many weeks to continue BID dosing after rifampicin stops.
      (Stored in the note for clinician reference; no programmatic stop.)

NOT DONE HERE
  - Alternate regimens (e.g., switch to EFV-based ART instead of BID DTG)
  - Rifabutin-based alternative TB regimens (different interaction profile)
  - Pediatric dosing
"""

from __future__ import annotations

from typing import Any

from daktaritb_mcp.fhir.client import FhirClient, FhirError
from daktaritb_mcp.fhir.context import FhirContext, MissingFhirContext
from daktaritb_mcp.fhir.schemas import (
    RXNORM_DTG_50MG,
    SNOMED_DDI_INTERACTION,
    detected_issue,
    medication_request,
)
from daktaritb_mcp.tools.base import ToolDefinition

# RxNorm code for TLD (our sample bundle uses this).
TLD_CODE = "2180325"
# Strings that indicate dolutegravir is in the medication name (fallback
# when codes vary across systems).
DTG_NAME_MARKERS = ("dolutegravir", "DTG", "TLD", "tenofovir/lamivudine/dolutegravir")
# Strings that indicate rifampicin is present.
RIFAMPICIN_NAME_MARKERS = ("rifampicin", "rifampin", "RHZE", "rifampicin/isoniazid")

# ICD-10 codes that indicate HIV positivity.
HIV_ICD10_CODES = {"B20", "Z21"}


def _is_hiv_positive(conditions: list[dict[str, Any]]) -> bool:
    for c in conditions:
        for coding in c.get("code", {}).get("coding", []):
            if coding.get("code") in HIV_ICD10_CODES:
                return True
    return False


def _find_medication(
    med_statements: list[dict[str, Any]], markers: tuple[str, ...]
) -> dict[str, Any] | None:
    """Find the first MedicationStatement whose text mentions any marker."""
    lower_markers = tuple(m.lower() for m in markers)
    for ms in med_statements:
        # Try coded text first
        text = (
            ms.get("medicationCodeableConcept", {}).get("text", "")
            or ms.get("medicationCodeableConcept", {}).get("coding", [{}])[0].get("display", "")
            or ""
        )
        if any(m in text.lower() for m in lower_markers):
            return ms
    return None


async def run(ctx: FhirContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute the tool."""
    if not ctx.has_patient:
        raise MissingFhirContext(
            "adjust_art_for_rif requires a patient-scoped context. "
            "No X-Patient-ID header was received."
        )

    confirm_rif = bool(arguments.get("confirm_rifampicin_present", False))
    continuation_weeks = int(arguments.get("continuation_weeks_post_rif", 2))
    if continuation_weeks < 0 or continuation_weeks > 8:
        raise ValueError(
            f"continuation_weeks_post_rif must be 0-8 (got {continuation_weeks})."
        )

    fhir = FhirClient(ctx)
    patient_id = ctx.patient_id or ""

    # --- Gather clinical context ---
    cond_bundle = await fhir.search(
        "Condition", {"patient": patient_id, "clinical-status": "active"}
    )
    conditions = FhirClient.extract_entries(cond_bundle)

    med_bundle = await fhir.search(
        "MedicationStatement", {"patient": patient_id, "status": "active"}
    )
    medications = FhirClient.extract_entries(med_bundle)

    # --- Validation: must be HIV+ ---
    if not _is_hiv_positive(conditions):
        return {
            "status": "skipped",
            "reason": "Patient does not appear HIV-positive. No ART adjustment needed.",
            "patient_id": patient_id,
        }

    # --- Validation: must be on DTG-based ART ---
    dtg_med = _find_medication(medications, DTG_NAME_MARKERS)
    if not dtg_med:
        return {
            "status": "skipped",
            "reason": (
                "Patient is HIV-positive but is not on dolutegravir-based ART. "
                "The rifampicin-DTG interaction only applies to DTG regimens."
            ),
            "patient_id": patient_id,
        }

    # --- Validation: rifampicin must be on board (or confirmed about to start) ---
    rif_med = _find_medication(medications, RIFAMPICIN_NAME_MARKERS)
    if not rif_med and not confirm_rif:
        return {
            "status": "skipped",
            "reason": (
                "Rifampicin is not currently in the patient's active medications "
                "and confirm_rifampicin_present was not set. If rifampicin is "
                "about to be started, retry with confirm_rifampicin_present=true."
            ),
            "patient_id": patient_id,
            "dtg_medication_id": dtg_med.get("id"),
        }

    dtg_ref = f"MedicationStatement/{dtg_med['id']}" if dtg_med.get("id") else None
    rif_ref = f"MedicationStatement/{rif_med['id']}" if rif_med and rif_med.get("id") else None

    # --- Step 1: Create a DetectedIssue documenting the interaction ---
    implicated: list[str] = []
    if dtg_ref:
        implicated.append(dtg_ref)
    if rif_ref:
        implicated.append(rif_ref)

    issue_detail = (
        "Dolutegravir (DTG) + Rifampicin: rifampicin is a potent inducer of "
        "UGT1A1, the enzyme responsible for DTG metabolism. Co-administration "
        "reduces DTG plasma concentrations significantly, risking virologic "
        "failure and resistance. Mitigation: supplement DTG with an additional "
        "50mg dose 12 hours after the main TLD dose, maintaining 50mg twice "
        f"daily (BID) dosing. Continue BID dosing for {continuation_weeks} "
        "weeks after rifampicin is discontinued due to lingering enzyme "
        "induction."
    )

    issue = detected_issue(
        patient_id=patient_id,
        severity="moderate",
        issue_code=SNOMED_DDI_INTERACTION,
        issue_display="Drug interaction",
        detail=issue_detail,
        implicated_references=implicated or None,
        evidence_detail="WHO Consolidated ARV Guidelines (2021); Kenya MOH ART Guidelines",
        mitigation="DTG dose adjusted to 50mg BID per guideline",
    )

    try:
        created_issue = await fhir.create(issue)
    except FhirError as e:
        return {
            "status": "error",
            "step_failed": "create_detected_issue",
            "error": str(e),
            "patient_id": patient_id,
        }

    issue_id = created_issue.get("id")
    issue_ref = f"DetectedIssue/{issue_id}" if issue_id else None

    # --- Step 2: Create updated MedicationRequest for DTG 50mg BID ---
    supplementary_dtg_note = (
        "Supplementary 50mg dolutegravir dose to be added to existing TLD "
        "(once-daily) to achieve effective 50mg BID dolutegravir dosing. "
        "Given ~12 hours after the main TLD dose. Continue for the duration "
        f"of rifampicin therapy plus {continuation_weeks} weeks."
    )

    new_rx = medication_request(
        patient_id=patient_id,
        medication_code=RXNORM_DTG_50MG,
        medication_display="Dolutegravir 50 mg oral tablet",
        dose_quantity_value=50.0,
        dose_unit="mg",
        dose_unit_code="mg",
        dose_frequency=2,
        dose_period=1.0,
        dose_period_unit="d",
        priority="routine",
        reason_text=(
            "Supplemental dolutegravir to compensate for rifampicin-induced "
            "UGT1A1 induction during TB treatment"
        ),
        supersedes=None,  # TLD OD continues; this is ADDITIVE, not replacing
        detected_issue=issue_ref,
        note=supplementary_dtg_note,
    )

    try:
        created_rx = await fhir.create(new_rx)
    except FhirError as e:
        return {
            "status": "error",
            "step_failed": "create_medication_request",
            "error": str(e),
            "detected_issue_id": issue_id,
            "patient_id": patient_id,
        }

    rx_id = created_rx.get("id")

    # --- Summary ---
    summary = (
        f"ART adjusted for rifampicin co-administration. "
        f"Created DetectedIssue {issue_id} + added supplementary DTG 50mg BID."
    )

    return {
        "status": "ok",
        "patient_id": patient_id,
        "hiv_positive": True,
        "dtg_medication_id": dtg_med.get("id"),
        "rifampicin_medication_id": rif_med.get("id") if rif_med else None,
        "rifampicin_assumed_present": bool(confirm_rif and not rif_med),
        "continuation_weeks_post_rif": continuation_weeks,
        "detected_issue": {
            "id": issue_id,
            "reference": issue_ref,
            "severity": "moderate",
            "code": SNOMED_DDI_INTERACTION,
        },
        "new_prescription": {
            "id": rx_id,
            "reference": f"MedicationRequest/{rx_id}" if rx_id else None,
            "medication": "Dolutegravir 50 mg",
            "dosing": "BID (every 12 hours)",
            "duration": f"For duration of rifampicin + {continuation_weeks} weeks",
        },
        "summary": summary,
    }


adjust_art_for_rif_tool = ToolDefinition(
    name="adjust_art_for_rif",
    description=(
        "Handle the dolutegravir-rifampicin drug interaction for PLHIV on TLD "
        "who are on (or starting) rifampicin-based TB treatment. Creates a "
        "DetectedIssue formally documenting the UGT1A1 interaction and adds a "
        "supplementary 50mg DTG prescription to achieve effective 50mg BID "
        "dosing per WHO and Kenya MOH guidelines. "
        "Safe to call: no-ops if patient is not HIV-positive or not on DTG."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "confirm_rifampicin_present": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Set to true when rifampicin is about to be started but is "
                    "not yet in the patient's medication list. If false, the "
                    "tool skips the adjustment when rifampicin is not detected."
                ),
            },
            "continuation_weeks_post_rif": {
                "type": "integer",
                "default": 2,
                "minimum": 0,
                "maximum": 8,
                "description": (
                    "Weeks to continue DTG BID dosing after rifampicin is stopped. "
                    "Default 2 per WHO guidance (covers residual enzyme induction)."
                ),
            },
        },
        "additionalProperties": False,
    },
    impl=run,
    requires_patient=True,
    annotations={
        "5T": "Transaction",
        "scope": "patient",
        "writes_fhir": True,
        "writes": ["DetectedIssue", "MedicationRequest"],
    },
)
