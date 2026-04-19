"""Kenya NTLD-P TB notification data model.

Derived from Kenya MOH's case-based TB surveillance tool (TIBU) schema and
the historical TB-001 paper form. The fields here represent what a facility
TB coordinator must report when a new TB case is diagnosed.

Key fields per Kenya NTLD-P 2023 guidance:
  - Patient demographics (name, sex, DOB, address, NHIF/national ID)
  - Facility identifiers (KMFL code, facility name, county)
  - Disease classification:
      * Anatomical site (pulmonary / extrapulmonary)
      * Bacteriological status (confirmed / clinically-diagnosed)
      * Case type (new, relapse, treatment-after-failure, etc.)
      * Drug susceptibility (DS-TB vs DR-TB)
  - HIV status (positive / negative / unknown) — NTLD-P requires 100% HIV testing for TB cases
  - Treatment regimen + start date
  - Notifier identity + notification date

We fill what we can from the FHIR chart and mark unknowns explicitly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


# --- Controlled vocabularies aligned with NTLD-P TB-001 ---

CASE_TYPE_NEW = "new"
CASE_TYPE_RELAPSE = "relapse"
CASE_TYPE_AFTER_LOSS = "treatment_after_loss_to_followup"
CASE_TYPE_AFTER_FAILURE = "treatment_after_failure"
CASE_TYPE_OTHER_PREVIOUS = "other_previously_treated"
CASE_TYPE_UNKNOWN = "unknown_previous_treatment"

SITE_PULMONARY = "pulmonary"
SITE_EXTRAPULMONARY = "extrapulmonary"

BACT_CONFIRMED = "bacteriologically_confirmed"
BACT_CLINICAL = "clinically_diagnosed"

HIV_POSITIVE = "positive"
HIV_NEGATIVE = "negative"
HIV_UNKNOWN = "unknown"

DR_STATUS_DS = "drug_sensitive"
DR_STATUS_DR = "drug_resistant"
DR_STATUS_UNKNOWN = "resistance_unknown"


@dataclass
class FacilityInfo:
    kmfl_code: str = ""
    name: str = ""
    county: str = "Nairobi"          # default for demo data
    sub_county: str = ""


@dataclass
class PatientInfo:
    fhir_id: str = ""
    upi: str = ""                    # Kenya Universal Patient Identifier
    family_name: str = ""
    given_name: str = ""
    sex: str = ""                    # "male" | "female" | "other"
    date_of_birth: str = ""          # ISO date, empty if unknown
    age_years: int | None = None     # computed from DOB if present
    address_city: str = ""
    phone: str = ""


@dataclass
class DiseaseInfo:
    onset_date: str = ""
    site: str = SITE_PULMONARY
    bacteriological_status: str = BACT_CLINICAL
    case_type: str = CASE_TYPE_NEW
    drug_resistance_status: str = DR_STATUS_DS
    icd10_code: str = ""
    description: str = ""


@dataclass
class DiagnosticFindings:
    genexpert_result: str = ""
    genexpert_date: str = ""
    afb_smear_result: str = ""
    afb_smear_date: str = ""
    chest_xray_result: str = ""
    culture_result: str = ""


@dataclass
class HIVInfo:
    status: str = HIV_UNKNOWN
    cd4_count: float | None = None
    cd4_date: str = ""
    viral_load: float | None = None
    viral_load_date: str = ""
    on_art: bool = False
    art_regimen: str = ""
    art_start_date: str = ""
    cotrimoxazole_preventive_therapy: bool = False


@dataclass
class TreatmentInfo:
    regimen: str = ""
    start_date: str = ""
    phase: str = "intensive"         # "intensive" | "continuation"
    dot_supporter_name: str = ""
    dot_supporter_relation: str = ""
    dot_supporter_phone: str = ""


@dataclass
class NotifierInfo:
    name: str = "DaktariTB MCP Agent"
    role: str = "Automated clinical decision support system"
    date: str = ""                   # ISO date


@dataclass
class TbNotification:
    """Top-level Kenya NTLD-P TB notification record."""

    facility: FacilityInfo = field(default_factory=FacilityInfo)
    patient: PatientInfo = field(default_factory=PatientInfo)
    disease: DiseaseInfo = field(default_factory=DiseaseInfo)
    diagnostic_findings: DiagnosticFindings = field(default_factory=DiagnosticFindings)
    hiv: HIVInfo = field(default_factory=HIVInfo)
    treatment: TreatmentInfo = field(default_factory=TreatmentInfo)
    notifier: NotifierInfo = field(default_factory=NotifierInfo)

    # Fields flagged as missing from the chart. Populated by the builder
    # and displayed on the form so reviewers can fill them manually.
    missing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_age_years(birth_date: str | None, as_of: date | None = None) -> int | None:
    """Return age in years from an ISO birth date string."""
    if not birth_date:
        return None
    try:
        dob = datetime.fromisoformat(birth_date).date()
    except ValueError:
        return None
    today = as_of or date.today()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return max(years, 0)
