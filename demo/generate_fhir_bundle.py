"""
DaktariTB FHIR Bundle Generator

Generates a FHIR R4 transaction bundle with 5 synthetic patient scenarios
representing real African TB/HIV co-infection clinical patterns.

Output: daktaritb_sample_bundle.json

All patients are entirely fictional. No real patient data is used.
"""

import json
import uuid
from datetime import datetime, timedelta

TODAY = datetime(2026, 4, 18)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S+03:00")


def date_only(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def urn(prefix: str) -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def patient_entry(full_url, patient_id, family, given, gender, birth_date, city, upi):
    return {
        "fullUrl": full_url,
        "resource": {
            "resourceType": "Patient",
            "identifier": [
                {"system": "https://fhir.kenyahmis.org/upi", "value": upi},
            ],
            "active": True,
            "name": [{"use": "official", "family": family, "given": given}],
            "gender": gender,
            "birthDate": birth_date,
            "address": [{"use": "home", "city": city, "country": "KE"}],
        },
        "request": {"method": "POST", "url": "Patient"},
    }


def condition_entry(patient_url, icd10, display, onset, active=True):
    status_code = "active" if active else "resolved"
    return {
        "fullUrl": urn("cond"),
        "resource": {
            "resourceType": "Condition",
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": status_code,
                    }
                ]
            },
            "code": {
                "coding": [
                    {"system": "http://hl7.org/fhir/sid/icd-10", "code": icd10, "display": display}
                ],
                "text": display,
            },
            "subject": {"reference": patient_url},
            "onsetDateTime": onset,
        },
        "request": {"method": "POST", "url": "Condition"},
    }


def med_statement_entry(patient_url, display, start_date):
    return {
        "fullUrl": urn("meds"),
        "resource": {
            "resourceType": "MedicationStatement",
            "status": "active",
            "medicationCodeableConcept": {
                "coding": [
                    {"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": display}
                ],
                "text": display,
            },
            "subject": {"reference": patient_url},
            "effectivePeriod": {"start": start_date},
        },
        "request": {"method": "POST", "url": "MedicationStatement"},
    }


def observation_entry(patient_url, loinc, display, value, unit, effective_date):
    return {
        "fullUrl": urn("obs"),
        "resource": {
            "resourceType": "Observation",
            "status": "final",
            "code": {
                "coding": [{"system": "http://loinc.org", "code": loinc, "display": display}],
                "text": display,
            },
            "subject": {"reference": patient_url},
            "effectiveDateTime": effective_date,
            "valueQuantity": {
                "value": value,
                "unit": unit,
                "system": "http://unitsofmeasure.org",
                "code": unit,
            },
        },
        "request": {"method": "POST", "url": "Observation"},
    }


def build_bundle():
    entries = []

    # --- PATIENT 1: Wanjiru Kamau — PLHIV, presumptive TB (the classic hero case) ---
    wanjiru_url = urn("pat")
    entries.append(
        patient_entry(wanjiru_url, None, "Kamau", ["Wanjiru"], "female", "1991-06-14", "Nairobi", "KE-WANJ001")
    )
    entries.append(
        condition_entry(wanjiru_url, "B20", "HIV disease (AIDS)", "2022-11-10")
    )
    entries.append(
        med_statement_entry(wanjiru_url, "Tenofovir/Lamivudine/Dolutegravir (TLD)", "2022-11-20")
    )
    # CD4 dropped from 480 to 290 over 6 months
    entries.append(observation_entry(wanjiru_url, "24467-3", "CD4 count", 480, "cells/uL", iso(TODAY - timedelta(days=180))))
    entries.append(observation_entry(wanjiru_url, "24467-3", "CD4 count", 290, "cells/uL", iso(TODAY - timedelta(days=7))))
    # VL suppressed
    entries.append(observation_entry(wanjiru_url, "25836-8", "HIV viral load", 40, "copies/mL", iso(TODAY - timedelta(days=7))))
    # Weight loss
    entries.append(observation_entry(wanjiru_url, "29463-7", "Body weight", 68, "kg", iso(TODAY - timedelta(days=180))))
    entries.append(observation_entry(wanjiru_url, "29463-7", "Body weight", 60, "kg", iso(TODAY - timedelta(days=7))))
    # Symptoms
    entries.append(observation_entry(wanjiru_url, "8310-5", "Body temperature", 38.4, "Cel", iso(TODAY - timedelta(days=2))))

    # --- PATIENT 2: Joseph Otieno — PLHIV stable, NO TB (negative control) ---
    joseph_url = urn("pat")
    entries.append(
        patient_entry(joseph_url, None, "Otieno", ["Joseph"], "male", "1983-11-22", "Kisumu", "KE-JOSE002")
    )
    entries.append(condition_entry(joseph_url, "B20", "HIV disease", "2020-03-15"))
    entries.append(med_statement_entry(joseph_url, "Tenofovir/Lamivudine/Dolutegravir (TLD)", "2020-03-20"))
    entries.append(observation_entry(joseph_url, "24467-3", "CD4 count", 720, "cells/uL", iso(TODAY - timedelta(days=30))))
    entries.append(observation_entry(joseph_url, "25836-8", "HIV viral load", 20, "copies/mL", iso(TODAY - timedelta(days=30))))

    # --- PATIENT 3: Amina Hassan — HIV-negative, active TB on RHZE ---
    amina_url = urn("pat")
    entries.append(
        patient_entry(amina_url, None, "Hassan", ["Amina"], "female", "1997-04-03", "Mombasa", "KE-AMIN003")
    )
    entries.append(condition_entry(amina_url, "A15.0", "Tuberculosis of lung, confirmed", "2026-02-15"))
    entries.append(
        med_statement_entry(
            amina_url,
            "Rifampicin/Isoniazid/Pyrazinamide/Ethambutol (RHZE) fixed-dose combination",
            "2026-02-20",
        )
    )

    # --- PATIENT 4: Grace Njeri — Newly diagnosed HIV, pre-ART, respiratory symptoms ---
    grace_url = urn("pat")
    entries.append(
        patient_entry(grace_url, None, "Njeri", ["Grace"], "female", "1999-09-18", "Nakuru", "KE-GRAC004")
    )
    entries.append(condition_entry(grace_url, "B20", "HIV disease (newly diagnosed)", date_only(TODAY - timedelta(days=10))))
    entries.append(observation_entry(grace_url, "24467-3", "CD4 count", 180, "cells/uL", iso(TODAY - timedelta(days=5))))
    entries.append(observation_entry(grace_url, "25836-8", "HIV viral load", 85000, "copies/mL", iso(TODAY - timedelta(days=5))))
    # No ART yet — pre-treatment

    # --- PATIENT 5: Samuel Kiprop — Co-infected (HIV+ on TLD + TB on RHZE) — the hero ---
    samuel_url = urn("pat")
    entries.append(
        patient_entry(samuel_url, None, "Kiprop", ["Samuel"], "male", "1987-02-11", "Eldoret", "KE-SAMU005")
    )
    entries.append(condition_entry(samuel_url, "B20", "HIV disease", "2023-05-12"))
    entries.append(condition_entry(samuel_url, "A15.0", "Tuberculosis of lung, confirmed", "2026-03-28"))
    entries.append(
        med_statement_entry(
            samuel_url,
            "Tenofovir/Lamivudine/Dolutegravir 300mg/300mg/50mg once daily",
            "2023-06-01",
        )
    )
    entries.append(
        med_statement_entry(
            samuel_url,
            "Rifampicin/Isoniazid/Pyrazinamide/Ethambutol (RHZE) fixed-dose combination",
            "2026-03-31",
        )
    )
    entries.append(observation_entry(samuel_url, "24467-3", "CD4 count", 210, "cells/uL", iso(TODAY - timedelta(days=22))))
    entries.append(observation_entry(samuel_url, "25836-8", "HIV viral load", 80, "copies/mL", iso(TODAY - timedelta(days=22))))

    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries,
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    bundle = build_bundle()
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "daktaritb_sample_bundle.json")
    output.write_text(json.dumps(bundle, indent=2))
    print(f"Wrote {len(bundle['entry'])} entries across 5 patients to {output}")
