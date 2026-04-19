"""Declarative definitions of the 10 clinical benchmark scenarios.

Each scenario is a dataclass describing:
  - A clinical situation
  - FHIR inputs (patient, conditions, meds, observations)
  - Which DaktariTB tool to invoke
  - What tool arguments to pass
  - The expected tool response shape (assertions)
  - The guideline citation backing the expected output

Scenarios are designed to test BOTH positive cases (tool does the right
thing) AND negative cases (tool correctly refuses). A decision support
tool that over-fires is dangerous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tests.clinical.fixtures import (
    bundle,
    condition,
    medication_statement,
    observation_quantity,
    patient,
)


@dataclass
class Scenario:
    """A single benchmark scenario."""

    id: int
    name: str
    clinical_description: str
    tool: str
    tool_arguments: dict[str, Any]

    # FHIR fixtures (closures so each scenario has isolated state)
    patient_builder: Callable[[], dict[str, Any]]
    conditions: list[dict[str, Any]]
    medications: list[dict[str, Any]]
    observations: dict[str, list[dict[str, Any]]]  # LOINC code -> observations

    # Expected outcomes
    expected_status: str  # "ok" | "skipped"
    expected_assertions: list[Callable[[dict], bool]]
    guideline_citation: str
    guideline_rationale: str


# --- Scenario 1: HIV+, CD4=290, WHO 4-symptom positive → LF-LAM included ---
SCENARIO_1 = Scenario(
    id=1,
    name="High-risk PLHIV presumptive TB",
    clinical_description=(
        "34yo female, HIV+ on TLD for 3 years, CD4 dropped from 480 to 290 "
        "over 6 months, 4-week cough, 8kg weight loss, drenching night sweats. "
        "WHO 4-symptom screen positive. CD4 below 350 threshold."
    ),
    tool="order_tb_workup",
    tool_arguments={},
    patient_builder=lambda: patient(pid="s1-patient", family="Kamau", given="Wanjiru"),
    conditions=[
        condition(cid="s1-hiv", icd10="B20", display="HIV disease", pid="s1-patient"),
    ],
    medications=[
        medication_statement(
            mid="s1-tld",
            display="Tenofovir/Lamivudine/Dolutegravir (TLD)",
            pid="s1-patient",
        ),
    ],
    observations={
        "24467-3": [observation_quantity(oid="s1-cd4", loinc="24467-3", value=290, unit="cells/uL", pid="s1-patient")],
    },
    expected_status="ok",
    expected_assertions=[
        lambda r: "errors" in r and len(r["errors"]) == 0,  # success: tool completed without errors
        lambda r: r.get("hiv_positive") is True,
        lambda r: r.get("latest_cd4") == 290,
        lambda r: r.get("lf_lam_included") is True,
        lambda r: len(r.get("orders_created", [])) == 4,
        lambda r: any(o["code"] == "95745-4" for o in r.get("orders_created", [])),  # LF-LAM
        lambda r: any(o["code"] == "88142-3" for o in r.get("orders_created", [])),  # GeneXpert
    ],
    guideline_citation="WHO Consolidated ART Guidelines (2021), §10.2",
    guideline_rationale=(
        "Urine LF-LAM is indicated for PLHIV with CD4 below 350 cells/µL. "
        "CD4 of 290 crosses this threshold. Standard TB workup also "
        "requires GeneXpert MTB/RIF, AFB smear, and chest X-ray."
    ),
)

# --- Scenario 2: HIV+, CD4=720, mild cough → NO LF-LAM ---
SCENARIO_2 = Scenario(
    id=2,
    name="PLHIV with high CD4 — LF-LAM not indicated",
    clinical_description=(
        "42yo male, HIV+ stable on TLD, CD4 720, mild 1-week cough. "
        "WHO screen borderline positive. CD4 well above 350 threshold."
    ),
    tool="order_tb_workup",
    tool_arguments={},
    patient_builder=lambda: patient(pid="s2-patient", family="Otieno", given="Joseph", gender="male"),
    conditions=[
        condition(cid="s2-hiv", icd10="B20", display="HIV disease", pid="s2-patient"),
    ],
    medications=[
        medication_statement(mid="s2-tld", display="TLD", pid="s2-patient"),
    ],
    observations={
        "24467-3": [observation_quantity(oid="s2-cd4", loinc="24467-3", value=720, unit="cells/uL", pid="s2-patient")],
    },
    expected_status="ok",
    expected_assertions=[
        lambda r: "errors" in r and len(r["errors"]) == 0,  # success: tool completed without errors
        lambda r: r.get("hiv_positive") is True,
        lambda r: r.get("lf_lam_included") is False,
        lambda r: len(r.get("orders_created", [])) == 3,
        lambda r: not any(o["code"] == "95745-4" for o in r.get("orders_created", [])),
    ],
    guideline_citation="WHO Consolidated ART Guidelines (2021), §10.2",
    guideline_rationale=(
        "Urine LF-LAM is NOT routinely indicated for PLHIV with CD4 at or "
        "above 350 cells/µL. Over-ordering LF-LAM in high-CD4 patients "
        "wastes scarce resources and produces false positives."
    ),
)

# --- Scenario 3: HIV-negative adult with cough → standard workup, no LF-LAM ---
SCENARIO_3 = Scenario(
    id=3,
    name="HIV-negative adult presumptive TB",
    clinical_description=(
        "28yo female, HIV-negative, 3-week productive cough and low-grade "
        "fever. No immunocompromise. Standard TB workup required; LF-LAM "
        "is HIV-specific and should not be ordered."
    ),
    tool="order_tb_workup",
    tool_arguments={},
    patient_builder=lambda: patient(pid="s3-patient", family="Hassan", given="Amina"),
    conditions=[],  # No HIV
    medications=[],
    observations={},
    expected_status="ok",
    expected_assertions=[
        lambda r: "errors" in r and len(r["errors"]) == 0,  # success: tool completed without errors
        lambda r: r.get("hiv_positive") is False,
        lambda r: r.get("lf_lam_included") is False,
        lambda r: len(r.get("orders_created", [])) == 3,
        lambda r: any(o["code"] == "88142-3" for o in r.get("orders_created", [])),
        lambda r: any(o["code"] == "648-0" for o in r.get("orders_created", [])),
        lambda r: any(o["code"] == "36554-4" for o in r.get("orders_created", [])),
    ],
    guideline_citation="WHO Operational Handbook on TB (2022), Module 3",
    guideline_rationale=(
        "HIV-negative patients with presumptive TB receive GeneXpert MTB/RIF "
        "as first-line, plus AFB smear and chest X-ray. Urine LF-LAM is a "
        "TB antigen detection test validated only in PLHIV and is not "
        "recommended for HIV-negative patients."
    ),
)

# --- Scenario 4: HIV+, CD4=140, severely ill → STAT workup ---
SCENARIO_4 = Scenario(
    id=4,
    name="Severely immunocompromised PLHIV — STAT workup",
    clinical_description=(
        "35yo male, HIV+ on TLD, CD4 140, severely ill with fever and "
        "respiratory distress. CD4 below 200 indicates advanced HIV; "
        "STAT priority justified for TB workup."
    ),
    tool="order_tb_workup",
    tool_arguments={"urgency": "stat"},
    patient_builder=lambda: patient(pid="s4-patient", family="Test", given="Severely-Ill", gender="male"),
    conditions=[
        condition(cid="s4-hiv", icd10="B20", display="HIV disease", pid="s4-patient"),
    ],
    medications=[
        medication_statement(mid="s4-tld", display="TLD", pid="s4-patient"),
    ],
    observations={
        "24467-3": [observation_quantity(oid="s4-cd4", loinc="24467-3", value=140, unit="cells/uL", pid="s4-patient")],
    },
    expected_status="ok",
    expected_assertions=[
        lambda r: "errors" in r and len(r["errors"]) == 0,  # success: tool completed without errors
        lambda r: r.get("urgency") == "stat",
        lambda r: r.get("lf_lam_included") is True,  # CD4<350 and <200 definitely
        lambda r: len(r.get("orders_created", [])) == 4,
    ],
    guideline_citation="WHO ART Guidelines §10.2 + Advanced HIV Disease recommendations",
    guideline_rationale=(
        "PLHIV with CD4 below 200 have advanced HIV disease and require "
        "urgent TB workup. STAT urgency reduces time-to-diagnosis and "
        "mortality. LF-LAM especially valuable in this population due to "
        "higher sensitivity in advanced immunosuppression."
    ),
)

# --- Scenario 5: HIV+ on TLD + rifampicin → DTG adjustment ---
SCENARIO_5 = Scenario(
    id=5,
    name="TB/HIV co-infection — DTG-rifampicin interaction management",
    clinical_description=(
        "38yo male, HIV+ on TLD for 3 years, newly diagnosed pulmonary TB "
        "started on RHZE (rifampicin-based regimen) 2 weeks ago. "
        "Rifampicin induces UGT1A1, lowering DTG plasma levels."
    ),
    tool="adjust_art_for_rif",
    tool_arguments={},
    patient_builder=lambda: patient(pid="s5-patient", family="Kiprop", given="Samuel", gender="male"),
    conditions=[
        condition(cid="s5-hiv", icd10="B20", display="HIV disease", pid="s5-patient"),
        condition(cid="s5-tb", icd10="A15.0", display="Tuberculosis of lung", pid="s5-patient"),
    ],
    medications=[
        medication_statement(mid="s5-tld", display="TLD", pid="s5-patient"),
        medication_statement(mid="s5-rhze", display="Rifampicin/Isoniazid/Pyrazinamide/Ethambutol (RHZE)", pid="s5-patient"),
    ],
    observations={},
    expected_status="ok",
    expected_assertions=[
        lambda r: r.get("status") == "ok",
        lambda r: r.get("hiv_positive") is True,
        lambda r: r.get("dtg_medication_id") is not None,
        lambda r: r.get("rifampicin_medication_id") is not None,
        lambda r: r.get("rifampicin_assumed_present") is False,
        lambda r: r.get("detected_issue", {}).get("severity") == "moderate",
        lambda r: r.get("new_prescription", {}).get("dosing") == "BID (every 12 hours)",
    ],
    guideline_citation="WHO Consolidated ARV Guidelines (2021) §4.4.3",
    guideline_rationale=(
        "When rifampicin is co-administered with dolutegravir, DTG dose "
        "must be doubled to 50mg twice daily to overcome UGT1A1 induction. "
        "This should be implemented as an additive supplementary dose to "
        "preserve the fixed-dose TLD combination, continuing for 2 weeks "
        "after rifampicin stops due to residual enzyme induction."
    ),
)

# --- Scenario 6: HIV+ on EFV + rifampicin → NO ADJUSTMENT ---
SCENARIO_6 = Scenario(
    id=6,
    name="EFV-based ART with rifampicin — no adjustment needed",
    clinical_description=(
        "45yo female, HIV+ on efavirenz-based ART (legacy regimen), TB "
        "on RHZE. EFV has a different pharmacokinetic profile and does "
        "not require dose adjustment for rifampicin co-administration."
    ),
    tool="adjust_art_for_rif",
    tool_arguments={},
    patient_builder=lambda: patient(pid="s6-patient", family="Test", given="EFV-Patient"),
    conditions=[
        condition(cid="s6-hiv", icd10="B20", display="HIV disease", pid="s6-patient"),
    ],
    medications=[
        medication_statement(mid="s6-efv", display="Efavirenz 600mg + Tenofovir + Lamivudine", pid="s6-patient"),
        medication_statement(mid="s6-rhze", display="Rifampicin/Isoniazid/Pyrazinamide/Ethambutol (RHZE)", pid="s6-patient"),
    ],
    observations={},
    expected_status="skipped",
    expected_assertions=[
        lambda r: r.get("status") == "skipped",
        lambda r: "dolutegravir" in r.get("reason", "").lower(),
    ],
    guideline_citation="WHO Consolidated ARV Guidelines (2021) §4.4.3",
    guideline_rationale=(
        "The UGT1A1 interaction affects dolutegravir specifically. "
        "Efavirenz-based regimens are metabolized primarily through CYP3A4/2B6 "
        "and do not require rifampicin dose adjustment. A decision support "
        "tool must correctly refuse to adjust regimens that don't need it."
    ),
)

# --- Scenario 7: HIV-negative on rifampicin → NO ADJUSTMENT ---
SCENARIO_7 = Scenario(
    id=7,
    name="HIV-negative TB patient — no ART adjustment",
    clinical_description=(
        "29yo female, HIV-negative, active TB on RHZE. No HIV means no "
        "ART, which means no drug interaction to manage."
    ),
    tool="adjust_art_for_rif",
    tool_arguments={},
    patient_builder=lambda: patient(pid="s7-patient", family="Test", given="HIV-Negative"),
    conditions=[
        condition(cid="s7-tb", icd10="A15.0", display="Tuberculosis of lung", pid="s7-patient"),
    ],
    medications=[
        medication_statement(mid="s7-rhze", display="RHZE", pid="s7-patient"),
    ],
    observations={},
    expected_status="skipped",
    expected_assertions=[
        lambda r: r.get("status") == "skipped",
        lambda r: "hiv" in r.get("reason", "").lower(),
    ],
    guideline_citation="Kenya NTLD-P Integrated Guidelines for TB/HIV Care",
    guideline_rationale=(
        "ART adjustment for rifampicin is only clinically meaningful for "
        "PLHIV receiving dolutegravir. The tool must refuse to adjust a "
        "regimen that doesn't exist. Over-firing here would fabricate a "
        "prescription for a non-existent patient need."
    ),
)

# --- Scenario 8: HIV+ on TLD, no rifampicin, no confirm flag → SKIP ---
SCENARIO_8 = Scenario(
    id=8,
    name="PLHIV on TLD without rifampicin — no adjustment",
    clinical_description=(
        "31yo female, HIV+ on TLD, no TB, no rifampicin in chart. "
        "Without rifampicin co-administration there is no interaction to "
        "manage. Pre-emptive adjustment is unsafe."
    ),
    tool="adjust_art_for_rif",
    tool_arguments={},
    patient_builder=lambda: patient(pid="s8-patient", family="Test", given="No-TB"),
    conditions=[
        condition(cid="s8-hiv", icd10="B20", display="HIV disease", pid="s8-patient"),
    ],
    medications=[
        medication_statement(mid="s8-tld", display="TLD", pid="s8-patient"),
    ],
    observations={},
    expected_status="skipped",
    expected_assertions=[
        lambda r: r.get("status") == "skipped",
        lambda r: "rifampicin" in r.get("reason", "").lower(),
    ],
    guideline_citation="Pharmacovigilance principle: no intervention without indication",
    guideline_rationale=(
        "DTG 50mg BID dosing is only indicated during rifampicin "
        "co-administration. Prescribing BID dosing to a patient not on "
        "rifampicin would expose them to unnecessary drug burden without "
        "clinical benefit."
    ),
)

# --- Scenario 9: A15.0 pulmonary TB → confirmed pulmonary notification ---
SCENARIO_9 = Scenario(
    id=9,
    name="Bacteriologically confirmed pulmonary TB — notification",
    clinical_description=(
        "Confirmed pulmonary TB (ICD-10 A15.0). Case must be notified to "
        "Kenya NTLD-P via TIBU. Classification: pulmonary (A15 prefix), "
        "bacteriologically confirmed (A15.0 specifically)."
    ),
    tool="generate_tb_notification",
    tool_arguments={},
    patient_builder=lambda: patient(pid="s9-patient", family="Test", given="Pulmonary-TB"),
    conditions=[
        condition(cid="s9-tb", icd10="A15.0", display="Tuberculosis of lung, confirmed", pid="s9-patient"),
    ],
    medications=[],
    observations={},
    expected_status="ok",
    expected_assertions=[
        lambda r: r.get("status") == "ok",
        lambda r: r.get("tb_condition", {}).get("icd10") == "A15.0",
        lambda r: r.get("tb_condition", {}).get("site") == "pulmonary",
        lambda r: r.get("tb_condition", {}).get("bacteriological_status") == "bacteriologically_confirmed",
        lambda r: r.get("document_reference", {}).get("size_bytes", 0) > 1000,  # real PDF
    ],
    guideline_citation="Kenya NTLD-P Case Definitions (2024 update)",
    guideline_rationale=(
        "ICD-10 A15.x codes designate bacteriologically confirmed pulmonary "
        "TB, where a specimen has been positive by smear, culture, or WHO-"
        "approved molecular test. A16.x codes indicate clinically diagnosed "
        "pulmonary TB. The notification tool must distinguish these."
    ),
)

# --- Scenario 10: A18.0 extrapulmonary TB → extrapulmonary clinical classification ---
SCENARIO_10 = Scenario(
    id=10,
    name="Extrapulmonary TB (bone and joint) — notification",
    clinical_description=(
        "Tuberculosis of bones and joints (ICD-10 A18.0). Extrapulmonary "
        "TB requires different treatment duration and monitoring. "
        "Classification: extrapulmonary (A18 prefix), clinically diagnosed."
    ),
    tool="generate_tb_notification",
    tool_arguments={"include_hiv_section": False},
    patient_builder=lambda: patient(pid="s10-patient", family="Test", given="Extrapulm-TB"),
    conditions=[
        condition(cid="s10-tb", icd10="A18.0", display="Tuberculosis of bones and joints", pid="s10-patient"),
    ],
    medications=[],
    observations={},
    expected_status="ok",
    expected_assertions=[
        lambda r: r.get("status") == "ok",
        lambda r: r.get("tb_condition", {}).get("icd10") == "A18.0",
        lambda r: r.get("tb_condition", {}).get("site") == "extrapulmonary",
        lambda r: r.get("tb_condition", {}).get("bacteriological_status") == "clinically_diagnosed",
    ],
    guideline_citation="Kenya NTLD-P Case Definitions (2024 update)",
    guideline_rationale=(
        "ICD-10 A17-A19 codes designate extrapulmonary TB. A18.0 specifically "
        "indicates osteoarticular TB. Extrapulmonary cases are typically "
        "clinically diagnosed because obtaining bacteriological confirmation "
        "is difficult (requires tissue sampling). Treatment duration may be "
        "extended (up to 9-12 months for CNS or bone involvement)."
    ),
)


ALL_SCENARIOS: list[Scenario] = [
    SCENARIO_1, SCENARIO_2, SCENARIO_3, SCENARIO_4, SCENARIO_5,
    SCENARIO_6, SCENARIO_7, SCENARIO_8, SCENARIO_9, SCENARIO_10,
]
