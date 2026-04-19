"""generate_tb_notification — Kenya NTLD-P TB notification.

INTENT
  Produce a Kenya Ministry of Health TB case notification (historically the
  TB-001 paper form, operationally the TIBU case-based electronic record).
  Renders as a PDF, wraps in a FHIR DocumentReference, POSTs to the chart.

CLINICAL PREREQUISITES
  The patient must have an active TB Condition (A15, A16, A17, A18, A19).
  Without that, the tool returns status="skipped".

FIELDS PULLED FROM THE CHART
  Patient: name, DOB, gender, address, identifier (Patient resource)
  Disease: onset date, ICD-10 code, description (Condition A15-A19)
  Diagnostics: GeneXpert (LOINC 88142-3), AFB smear (LOINC 648-0),
               CD4 (LOINC 24467-3), viral load (LOINC 25836-8)
  HIV status: Condition B20/Z21, or Observation 75622-1
  ART: active MedicationStatement containing "dolutegravir", "TLD", etc.
  TB treatment: active MedicationStatement containing "RHZE", "rifampicin", etc.

FIELDS NOT IN THE CHART (flagged as missing for manual completion)
  DOT supporter name/relation/phone
  Sub-county (facility is county-level)
  Phone number (unless in Patient.telecom)

INPUTS
  Optional:
    treatment_phase: "intensive" | "continuation"  (default "intensive")
    include_hiv_section: bool  (default True; set False for privacy-sensitive
      rollouts where HIV status shouldn't be on the notification)
"""

from __future__ import annotations

import base64
from datetime import date
from typing import Any

from daktaritb_mcp.config import settings
from daktaritb_mcp.fhir.client import FhirClient, FhirError
from daktaritb_mcp.fhir.context import FhirContext, MissingFhirContext
from daktaritb_mcp.fhir.schemas import document_reference
from daktaritb_mcp.kenya_moh.pdf_renderer import render_pdf
from daktaritb_mcp.kenya_moh.tb_notification import (
    BACT_CLINICAL,
    BACT_CONFIRMED,
    HIV_NEGATIVE,
    HIV_POSITIVE,
    HIV_UNKNOWN,
    DiagnosticFindings,
    DiseaseInfo,
    FacilityInfo,
    HIVInfo,
    NotifierInfo,
    PatientInfo,
    SITE_EXTRAPULMONARY,
    SITE_PULMONARY,
    TbNotification,
    TreatmentInfo,
    compute_age_years,
)
from daktaritb_mcp.tools.base import ToolDefinition

# ICD-10 codes for TB (pulmonary and extrapulmonary).
TB_ICD10_PULMONARY_PREFIX = ("A15", "A16")
TB_ICD10_EXTRAPULMONARY_PREFIX = ("A17", "A18", "A19")
# Bacteriologically-confirmed TB codes.
TB_ICD10_CONFIRMED = {"A15.0", "A15.1", "A15.2", "A15.3", "A15.4", "A15.5",
                       "A15.6", "A15.7", "A15.8", "A15.9"}

HIV_ICD10_CODES = {"B20", "Z21"}

LOINC_CD4 = "24467-3"
LOINC_VIRAL_LOAD = "25836-8"
LOINC_GENEXPERT = "88142-3"
LOINC_AFB_SMEAR = "648-0"
LOINC_CXR = "36554-4"
LOINC_HIV_STATUS_OBS = "75622-1"


def _find_condition_tb(conditions: list[dict[str, Any]]) -> dict[str, Any] | None:
    for c in conditions:
        for coding in c.get("code", {}).get("coding", []):
            code = coding.get("code", "")
            if code.startswith(TB_ICD10_PULMONARY_PREFIX + TB_ICD10_EXTRAPULMONARY_PREFIX):
                return c
    return None


def _is_hiv_positive_from_conditions(conditions: list[dict[str, Any]]) -> bool:
    for c in conditions:
        for coding in c.get("code", {}).get("coding", []):
            if coding.get("code") in HIV_ICD10_CODES:
                return True
    return False


def _latest_observation(bundle_entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the most recent Observation entry by effectiveDateTime."""
    with_dates = [
        (o.get("effectiveDateTime", ""), o) for o in bundle_entries
    ]
    with_dates.sort(key=lambda x: x[0], reverse=True)
    return with_dates[0][1] if with_dates else None


def _medication_display(med: dict[str, Any]) -> str:
    return (
        med.get("medicationCodeableConcept", {}).get("text", "")
        or med.get("medicationCodeableConcept", {}).get("coding", [{}])[0].get("display", "")
        or ""
    )


def _find_medication(
    med_statements: list[dict[str, Any]], markers: tuple[str, ...]
) -> dict[str, Any] | None:
    lower_markers = tuple(m.lower() for m in markers)
    for ms in med_statements:
        if any(m in _medication_display(ms).lower() for m in lower_markers):
            return ms
    return None


async def run(ctx: FhirContext, arguments: dict[str, Any]) -> dict[str, Any]:
    if not ctx.has_patient:
        raise MissingFhirContext(
            "generate_tb_notification requires a patient-scoped context. "
            "No X-Patient-ID header was received."
        )

    phase = arguments.get("treatment_phase", "intensive")
    if phase not in ("intensive", "continuation"):
        raise ValueError(f"Invalid treatment_phase '{phase}'. Must be 'intensive' or 'continuation'.")

    include_hiv = bool(arguments.get("include_hiv_section", True))

    fhir = FhirClient(ctx)
    patient_id = ctx.patient_id or ""

    # --- Patient resource ---
    try:
        patient_resource = await fhir.read("Patient", patient_id)
    except FhirError as e:
        return {
            "status": "error",
            "step_failed": "read_patient",
            "error": str(e),
            "patient_id": patient_id,
        }

    # --- Conditions + Medications ---
    cond_bundle = await fhir.search(
        "Condition", {"patient": patient_id, "clinical-status": "active"}
    )
    conditions = FhirClient.extract_entries(cond_bundle)

    tb_condition = _find_condition_tb(conditions)
    if not tb_condition:
        return {
            "status": "skipped",
            "reason": (
                "Patient has no active TB Condition (ICD-10 A15-A19) in their chart. "
                "TB notification cannot be generated without a confirmed or "
                "clinically-diagnosed TB diagnosis."
            ),
            "patient_id": patient_id,
        }

    med_bundle = await fhir.search(
        "MedicationStatement", {"patient": patient_id, "status": "active"}
    )
    medications = FhirClient.extract_entries(med_bundle)

    # --- Observations (for diagnostic findings + HIV markers) ---
    cd4_bundle = await fhir.search(
        "Observation", {"patient": patient_id, "code": LOINC_CD4, "_sort": "-date", "_count": "1"}
    )
    vl_bundle = await fhir.search(
        "Observation", {"patient": patient_id, "code": LOINC_VIRAL_LOAD, "_sort": "-date", "_count": "1"}
    )
    genexpert_bundle = await fhir.search(
        "Observation", {"patient": patient_id, "code": LOINC_GENEXPERT, "_sort": "-date", "_count": "1"}
    )
    afb_bundle = await fhir.search(
        "Observation", {"patient": patient_id, "code": LOINC_AFB_SMEAR, "_sort": "-date", "_count": "1"}
    )
    hiv_status_bundle = await fhir.search(
        "Observation", {"patient": patient_id, "code": LOINC_HIV_STATUS_OBS, "_sort": "-date", "_count": "1"}
    )

    cd4_obs = _latest_observation(FhirClient.extract_entries(cd4_bundle))
    vl_obs = _latest_observation(FhirClient.extract_entries(vl_bundle))
    genexpert_obs = _latest_observation(FhirClient.extract_entries(genexpert_bundle))
    afb_obs = _latest_observation(FhirClient.extract_entries(afb_bundle))
    hiv_status_obs = _latest_observation(FhirClient.extract_entries(hiv_status_bundle))

    # --- Build the notification record ---
    missing: list[str] = []
    notification = TbNotification()

    # Facility
    notification.facility = FacilityInfo(
        kmfl_code=settings.moh_facility_code or "UNASSIGNED",
        name=settings.moh_facility_name or "Unspecified Facility",
        county="Nairobi",
    )
    if not settings.moh_facility_code:
        missing.append("facility KMFL code")
    if not settings.moh_facility_name:
        missing.append("facility name")

    # Patient
    name = (patient_resource.get("name") or [{}])[0]
    identifier = (patient_resource.get("identifier") or [{}])[0]
    address = (patient_resource.get("address") or [{}])[0]
    telecom = (patient_resource.get("telecom") or [{}])[0]
    dob = patient_resource.get("birthDate", "")
    notification.patient = PatientInfo(
        fhir_id=patient_id,
        upi=identifier.get("value", ""),
        family_name=name.get("family", ""),
        given_name=" ".join(name.get("given", [])),
        sex=patient_resource.get("gender", ""),
        date_of_birth=dob,
        age_years=compute_age_years(dob) if dob else None,
        address_city=address.get("city", ""),
        phone=telecom.get("value", ""),
    )
    if not telecom.get("value"):
        missing.append("patient phone")

    # Disease
    tb_coding = tb_condition.get("code", {}).get("coding", [{}])[0]
    icd10 = tb_coding.get("code", "")
    is_confirmed = icd10 in TB_ICD10_CONFIRMED
    is_pulmonary = icd10.startswith(TB_ICD10_PULMONARY_PREFIX)
    notification.disease = DiseaseInfo(
        onset_date=tb_condition.get("onsetDateTime", ""),
        site=SITE_PULMONARY if is_pulmonary else SITE_EXTRAPULMONARY,
        bacteriological_status=BACT_CONFIRMED if is_confirmed else BACT_CLINICAL,
        case_type="new",
        drug_resistance_status="drug_sensitive",  # default; we don't infer DR-TB here
        icd10_code=icd10,
        description=tb_coding.get("display", "") or tb_condition.get("code", {}).get("text", ""),
    )

    # Diagnostic findings
    dx = DiagnosticFindings()
    if genexpert_obs:
        vc = genexpert_obs.get("valueCodeableConcept", {})
        dx.genexpert_result = vc.get("text") or (vc.get("coding") or [{}])[0].get("display", "")
        dx.genexpert_date = (genexpert_obs.get("effectiveDateTime", "") or "")[:10]
    if afb_obs:
        vc = afb_obs.get("valueCodeableConcept", {})
        dx.afb_smear_result = vc.get("text") or (vc.get("coding") or [{}])[0].get("display", "")
        dx.afb_smear_date = (afb_obs.get("effectiveDateTime", "") or "")[:10]
    notification.diagnostic_findings = dx

    # HIV section
    if include_hiv:
        hiv_positive = _is_hiv_positive_from_conditions(conditions)
        if hiv_status_obs and not hiv_positive:
            # Fallback: HIV status from observation
            vc = hiv_status_obs.get("valueCodeableConcept", {})
            obs_text = (vc.get("text") or (vc.get("coding") or [{}])[0].get("display", "")).lower()
            if "negative" in obs_text:
                hiv_status = HIV_NEGATIVE
            elif "positive" in obs_text:
                hiv_status = HIV_POSITIVE
            else:
                hiv_status = HIV_UNKNOWN
        else:
            hiv_status = HIV_POSITIVE if hiv_positive else HIV_UNKNOWN

        hiv = HIVInfo(status=hiv_status)

        if cd4_obs:
            hiv.cd4_count = cd4_obs.get("valueQuantity", {}).get("value")
            hiv.cd4_date = (cd4_obs.get("effectiveDateTime", "") or "")[:10]
        if vl_obs:
            hiv.viral_load = vl_obs.get("valueQuantity", {}).get("value")
            hiv.viral_load_date = (vl_obs.get("effectiveDateTime", "") or "")[:10]

        art_med = _find_medication(
            medications,
            ("dolutegravir", "TLD", "tenofovir/lamivudine/dolutegravir", "efavirenz"),
        )
        if art_med:
            hiv.on_art = True
            hiv.art_regimen = _medication_display(art_med)
            hiv.art_start_date = (
                art_med.get("effectivePeriod", {}).get("start", "") or ""
            )[:10]
        notification.hiv = hiv

        if hiv_status == HIV_UNKNOWN:
            missing.append("HIV test result (required by NTLD-P — all TB cases must be tested)")

    # Treatment
    tb_med = _find_medication(
        medications, ("rhze", "rifampicin/isoniazid", "rifampicin")
    )
    if tb_med:
        treatment = TreatmentInfo(
            regimen=_medication_display(tb_med),
            start_date=(tb_med.get("effectivePeriod", {}).get("start", "") or "")[:10],
            phase=phase,
        )
    else:
        treatment = TreatmentInfo(phase=phase)
        missing.append("TB treatment regimen details")
    missing.append("DOT supporter information")
    notification.treatment = treatment

    # Notifier
    notification.notifier = NotifierInfo(
        name="DaktariTB MCP Agent",
        role="Automated clinical decision support system",
        date=date.today().isoformat(),
    )

    notification.missing_fields = missing

    # --- Render PDF ---
    try:
        pdf_bytes = render_pdf(notification)
    except Exception as e:
        return {
            "status": "error",
            "step_failed": "pdf_render",
            "error": f"PDF rendering failed: {e}",
            "notification_data": notification.to_dict(),
            "patient_id": patient_id,
        }
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    # --- Build + POST DocumentReference ---
    related_conditions = [f"Condition/{tb_condition['id']}"] if tb_condition.get("id") else None
    doc_ref = document_reference(
        patient_id=patient_id,
        pdf_base64=pdf_base64,
        title=f"Kenya NTLD-P TB Notification — {notification.patient.given_name} {notification.patient.family_name}",
        description="TB case notification for submission to Kenya NTLD-P / TIBU surveillance system",
        related_conditions=related_conditions,
        facility_name=notification.facility.name,
        notification_date=date.today().isoformat(),
    )

    try:
        created_doc = await fhir.create(doc_ref)
    except FhirError as e:
        return {
            "status": "error",
            "step_failed": "create_document_reference",
            "error": str(e),
            "notification_data": notification.to_dict(),
            "patient_id": patient_id,
        }

    doc_id = created_doc.get("id")

    return {
        "status": "ok",
        "patient_id": patient_id,
        "tb_condition": {
            "id": tb_condition.get("id"),
            "icd10": notification.disease.icd10_code,
            "site": notification.disease.site,
            "bacteriological_status": notification.disease.bacteriological_status,
        },
        "notification_data": notification.to_dict(),
        "document_reference": {
            "id": doc_id,
            "reference": f"DocumentReference/{doc_id}" if doc_id else None,
            "content_type": "application/pdf",
            "size_bytes": len(pdf_bytes),
        },
        "missing_fields": missing,
        "summary": (
            f"Generated Kenya NTLD-P TB notification for {notification.patient.given_name} "
            f"{notification.patient.family_name} as a {len(pdf_bytes)}-byte PDF, stored as "
            f"DocumentReference {doc_id}."
            + (f" Fields pending manual completion: {', '.join(missing)}." if missing else "")
        ),
    }


generate_tb_notification_tool = ToolDefinition(
    name="generate_tb_notification",
    description=(
        "Generate a Kenya Ministry of Health TB case notification (historically "
        "TB-001; operationally TIBU). Pulls patient demographics, TB diagnosis, "
        "diagnostic findings (GeneXpert/AFB/CD4/VL), HIV status, and treatment "
        "regimen from the chart. Renders a PDF matching the NTLD-P notification "
        "structure, wraps it in a FHIR DocumentReference, and stores it in the "
        "patient's record. Flags any fields that couldn't be populated from "
        "chart data for manual completion before submission to TIBU."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "treatment_phase": {
                "type": "string",
                "enum": ["intensive", "continuation"],
                "default": "intensive",
                "description": "Current phase of TB treatment. 'intensive' for 2HRZE, 'continuation' for 4HR.",
            },
            "include_hiv_section": {
                "type": "boolean",
                "default": True,
                "description": "Whether to populate the TB/HIV integration section. Set false for privacy-sensitive rollouts.",
            },
        },
        "additionalProperties": False,
    },
    impl=run,
    requires_patient=True,
    annotations={
        "5T": "Template",
        "scope": "patient",
        "writes_fhir": True,
        "writes": ["DocumentReference"],
        "produces": ["application/pdf"],
    },
)
