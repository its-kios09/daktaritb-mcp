"""order_tb_workup — the first DaktariTB clinical tool.

INTENT
  Create FHIR ServiceRequest resources for a standard TB workup in a
  patient suspected of having active tuberculosis. Tailored to PLHIV:
  if the patient is HIV-positive with CD4 < 350, automatically includes
  a Urine LF-LAM order per WHO guidance.

INPUTS
  Optional:
    urgency: "routine" | "stat"  (default "routine")
    include_afb_smear: bool      (default True)
    include_chest_xray: bool     (default True)

CONTEXT REQUIRED
  X-FHIR-Server-URL, X-Patient-ID (access token optional per server)

BEHAVIOR
  1. Fetch patient's active Conditions (to cite HIV / TB in reasonReference)
  2. Fetch most recent CD4 count Observation (LOINC 24467-3)
  3. Determine which orders to place:
     - GeneXpert MTB/RIF         (always)
     - AFB smear                 (unless disabled)
     - Chest X-ray               (unless disabled)
     - Urine LF-LAM              (only if HIV+ AND CD4 < 350)
  4. POST ServiceRequest resources, one per order
  5. Return a summary with created FHIR IDs

NOT DONE HERE
  - DaktariAI clinical reasoning (Po's Gemini handles reasoning in the agent layer)
  - Writing notifications / tasks (those are separate tools)
  - Drug-resistant TB workflow (out of scope for v1)
"""

from __future__ import annotations

from typing import Any

from daktaritb_mcp.fhir.client import FhirClient, FhirError
from daktaritb_mcp.fhir.context import FhirContext, MissingFhirContext
from daktaritb_mcp.fhir.schemas import (
    LOINC_AFB_SMEAR,
    LOINC_CHEST_XRAY,
    LOINC_GENEXPERT_MTB_RIF,
    LOINC_LF_LAM,
    LOINC_SYSTEM,
    service_request,
)
from daktaritb_mcp.tools.base import ToolDefinition

# ICD-10 codes that indicate HIV positivity.
HIV_ICD10_CODES = {"B20", "Z21"}
# ICD-10 prefix for tuberculosis (A15, A16, A17, A18, A19).
TB_ICD10_PREFIX = "A1"
# LOINC code for CD4+ count.
LOINC_CD4 = "24467-3"
# WHO-recommended threshold for LF-LAM (cells/uL).
LF_LAM_CD4_THRESHOLD = 350


async def _active_conditions(fhir: FhirClient, patient_id: str) -> list[dict[str, Any]]:
    bundle = await fhir.search(
        "Condition",
        {"patient": patient_id, "clinical-status": "active"},
    )
    return FhirClient.extract_entries(bundle)


async def _latest_cd4(fhir: FhirClient, patient_id: str) -> float | None:
    """Return the most recent CD4 value, or None if no observation found."""
    bundle = await fhir.search(
        "Observation",
        {"patient": patient_id, "code": LOINC_CD4, "_sort": "-date", "_count": "1"},
    )
    obs_list = FhirClient.extract_entries(bundle)
    if not obs_list:
        return None
    value = obs_list[0].get("valueQuantity", {}).get("value")
    return float(value) if value is not None else None


def _is_hiv_positive(conditions: list[dict[str, Any]]) -> bool:
    for c in conditions:
        for coding in c.get("code", {}).get("coding", []):
            if coding.get("code") in HIV_ICD10_CODES:
                return True
    return False


def _condition_ids_of_interest(conditions: list[dict[str, Any]]) -> list[str]:
    """Return FHIR Condition/<id> references for HIV + TB + symptoms.

    These get attached as reasonReference on the ServiceRequests so the
    lab order clearly documents why it was placed.
    """
    refs: list[str] = []
    for c in conditions:
        cid = c.get("id")
        if not cid:
            continue
        for coding in c.get("code", {}).get("coding", []):
            code = coding.get("code", "")
            if code in HIV_ICD10_CODES or code.startswith(TB_ICD10_PREFIX):
                refs.append(f"Condition/{cid}")
                break
    return refs


async def run(ctx: FhirContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute the tool. Returns a structured result for the MCP client."""
    if not ctx.has_patient:
        raise MissingFhirContext(
            "order_tb_workup requires a patient-scoped context. "
            "No X-Patient-ID header was received."
        )

    urgency = arguments.get("urgency", "routine")
    if urgency not in ("routine", "stat"):
        raise ValueError(f"Invalid urgency '{urgency}'. Must be 'routine' or 'stat'.")

    include_afb = bool(arguments.get("include_afb_smear", True))
    include_cxr = bool(arguments.get("include_chest_xray", True))

    fhir = FhirClient(ctx)

    # Gather clinical context
    conditions = await _active_conditions(fhir, ctx.patient_id or "")
    reason_refs = _condition_ids_of_interest(conditions)
    hiv_positive = _is_hiv_positive(conditions)
    cd4 = await _latest_cd4(fhir, ctx.patient_id or "")

    # Decide on the order set
    orders: list[tuple[str, str, str]] = []
    orders.append((LOINC_GENEXPERT_MTB_RIF, "GeneXpert MTB/RIF", "laboratory"))
    if include_afb:
        orders.append((LOINC_AFB_SMEAR, "AFB sputum smear microscopy", "laboratory"))
    if include_cxr:
        orders.append((LOINC_CHEST_XRAY, "Chest X-ray", "imaging"))

    lf_lam_included = False
    if hiv_positive and cd4 is not None and cd4 < LF_LAM_CD4_THRESHOLD:
        orders.append((LOINC_LF_LAM, "Urine LF-LAM", "laboratory"))
        lf_lam_included = True

    # Build + POST each ServiceRequest
    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for code, display, category in orders:
        resource = service_request(
            patient_id=ctx.patient_id or "",
            code_system=LOINC_SYSTEM,
            code=code,
            display=display,
            category_code=category,
            category_display="Laboratory procedure" if category == "laboratory" else "Imaging",
            priority=urgency,
            reason_references=reason_refs or None,
            reason_text="Rule out active tuberculosis" if not reason_refs else None,
        )
        try:
            result = await fhir.create(resource)
            created.append({
                "code": code,
                "display": display,
                "fhir_id": result.get("id"),
                "reference": f"ServiceRequest/{result.get('id')}",
            })
        except FhirError as e:
            errors.append({
                "code": code,
                "display": display,
                "error": str(e),
                "status_code": e.status_code,
            })

    return {
        "patient_id": ctx.patient_id,
        "hiv_positive": hiv_positive,
        "latest_cd4": cd4,
        "urgency": urgency,
        "orders_created": created,
        "errors": errors,
        "lf_lam_included": lf_lam_included,
        "reason_references": reason_refs,
        "summary": (
            f"Ordered {len(created)} lab/imaging study(ies) for TB workup"
            + (f" (LF-LAM included: CD4={cd4})" if lf_lam_included else "")
            + (f" — {len(errors)} errors" if errors else "")
        ),
    }


# --- MCP tool declaration ---
order_tb_workup_tool = ToolDefinition(
    name="order_tb_workup",
    description=(
        "Place a standard TB workup as FHIR ServiceRequest resources in the "
        "patient's chart. Always orders GeneXpert MTB/RIF. Adds AFB smear and "
        "chest X-ray by default. If the patient is HIV-positive with CD4 < 350, "
        "automatically adds Urine LF-LAM per WHO guidance. Links orders to the "
        "patient's existing HIV/TB Conditions via reasonReference."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "urgency": {
                "type": "string",
                "enum": ["routine", "stat"],
                "default": "routine",
                "description": "Priority on the ServiceRequests. Use 'stat' for high-risk presentations (CD4 < 200, severely ill).",
            },
            "include_afb_smear": {
                "type": "boolean",
                "default": True,
                "description": "Include AFB sputum smear microscopy. Default true.",
            },
            "include_chest_xray": {
                "type": "boolean",
                "default": True,
                "description": "Include chest X-ray. Default true.",
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
    },
)
