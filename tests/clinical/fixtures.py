"""FHIR fixture builders for benchmark scenarios.

These are minimal but valid FHIR R4 resources used across the benchmark.
Each builder returns a dict that matches the FHIR R4 JSON structure.
"""

from __future__ import annotations

from typing import Any


def patient(
    *,
    pid: str = "bench-patient",
    family: str = "Test",
    given: str = "Patient",
    gender: str = "female",
    birth_date: str = "1990-01-01",
    city: str = "Nairobi",
) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": pid,
        "identifier": [{"system": "https://fhir.kenyahmis.org/upi", "value": f"KE-{pid.upper()}"}],
        "name": [{"use": "official", "family": family, "given": [given]}],
        "gender": gender,
        "birthDate": birth_date,
        "address": [{"use": "home", "city": city, "country": "KE"}],
    }


def condition(
    *,
    cid: str,
    icd10: str,
    display: str,
    active: bool = True,
    onset: str | None = None,
    pid: str = "bench-patient",
) -> dict[str, Any]:
    return {
        "resourceType": "Condition",
        "id": cid,
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active" if active else "resolved",
                }
            ]
        },
        "code": {
            "coding": [
                {"system": "http://hl7.org/fhir/sid/icd-10", "code": icd10, "display": display}
            ],
            "text": display,
        },
        "subject": {"reference": f"Patient/{pid}"},
        "onsetDateTime": onset or "2026-04-01",
    }


def medication_statement(
    *,
    mid: str,
    display: str,
    start: str = "2024-01-01",
    active: bool = True,
    pid: str = "bench-patient",
) -> dict[str, Any]:
    return {
        "resourceType": "MedicationStatement",
        "id": mid,
        "status": "active" if active else "stopped",
        "medicationCodeableConcept": {
            "coding": [
                {"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": display}
            ],
            "text": display,
        },
        "subject": {"reference": f"Patient/{pid}"},
        "effectivePeriod": {"start": start},
    }


def observation_quantity(
    *,
    oid: str,
    loinc: str,
    value: float,
    unit: str,
    date: str = "2026-04-10",
    pid: str = "bench-patient",
) -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "id": oid,
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc}]},
        "subject": {"reference": f"Patient/{pid}"},
        "effectiveDateTime": f"{date}T00:00:00+03:00",
        "valueQuantity": {"value": value, "unit": unit},
    }


def bundle(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": r} for r in entries],
    }
