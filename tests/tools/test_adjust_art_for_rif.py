"""Tests for adjust_art_for_rif.

Same MockTransport pattern as the other tool tests — fake FHIR server,
real clinical logic under test.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from daktaritb_mcp.fhir.context import FhirContext, MissingFhirContext
from daktaritb_mcp.tools.adjust_art_for_rif import run as adjust_art_for_rif

FHIR_BASE = "https://fhir.example.com"
PATIENT_ID = "patient-samuel"


def _condition(code: str, cid: str = "cond-hiv") -> dict[str, Any]:
    return {
        "resourceType": "Condition",
        "id": cid,
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "code": {
            "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": code}],
            "text": f"Code {code}",
        },
        "subject": {"reference": f"Patient/{PATIENT_ID}"},
    }


def _med_statement(display: str, mid: str) -> dict[str, Any]:
    return {
        "resourceType": "MedicationStatement",
        "id": mid,
        "status": "active",
        "medicationCodeableConcept": {
            "coding": [
                {"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "display": display}
            ],
            "text": display,
        },
        "subject": {"reference": f"Patient/{PATIENT_ID}"},
    }


def _bundle(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": r} for r in entries],
    }


def _transport_factory(
    conditions: list[dict[str, Any]], meds: list[dict[str, Any]]
) -> httpx.MockTransport:
    counter = {"issue": 0, "rx": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        method = request.method

        if method == "GET" and "/Condition" in url:
            return httpx.Response(200, json=_bundle(conditions))
        if method == "GET" and "/MedicationStatement" in url:
            return httpx.Response(200, json=_bundle(meds))
        if method == "POST" and "/DetectedIssue" in url:
            counter["issue"] += 1
            import json as _json

            body = _json.loads(request.content)
            body["id"] = f"issue-{counter['issue']}"
            return httpx.Response(201, json=body)
        if method == "POST" and "/MedicationRequest" in url:
            counter["rx"] += 1
            import json as _json

            body = _json.loads(request.content)
            body["id"] = f"rx-{counter['rx']}"
            return httpx.Response(201, json=body)

        return httpx.Response(404, json={"resourceType": "OperationOutcome"})

    return httpx.MockTransport(handler)


def _monkeypatch_httpx(monkeypatch, transport):
    original = httpx.AsyncClient

    class _Patched(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("daktaritb_mcp.fhir.client.httpx.AsyncClient", _Patched)


@pytest.mark.asyncio
async def test_requires_patient_context():
    ctx = FhirContext(server_url=FHIR_BASE, access_token=None, patient_id=None)
    with pytest.raises(MissingFhirContext):
        await adjust_art_for_rif(ctx, {})


@pytest.mark.asyncio
async def test_skips_non_hiv_patient(monkeypatch):
    """Patient without HIV: tool returns skipped status, no writes."""
    transport = _transport_factory(
        conditions=[_condition("A15.0", "cond-tb-only")],  # TB but no HIV
        meds=[_med_statement("Rifampicin/Isoniazid/Pyrazinamide/Ethambutol", "med-rhze")],
    )
    _monkeypatch_httpx(monkeypatch, transport)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await adjust_art_for_rif(ctx, {})

    assert result["status"] == "skipped"
    assert "HIV" in result["reason"]


@pytest.mark.asyncio
async def test_skips_hiv_no_dtg(monkeypatch):
    """HIV+ patient on EFV (not DTG): no adjustment needed."""
    transport = _transport_factory(
        conditions=[_condition("B20", "cond-hiv")],
        meds=[_med_statement("Efavirenz 600 mg", "med-efv")],
    )
    _monkeypatch_httpx(monkeypatch, transport)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await adjust_art_for_rif(ctx, {})

    assert result["status"] == "skipped"
    assert "dolutegravir" in result["reason"].lower()


@pytest.mark.asyncio
async def test_skips_no_rifampicin_without_confirm(monkeypatch):
    """HIV+, on DTG, but no rifampicin in chart and no confirm flag: skip."""
    transport = _transport_factory(
        conditions=[_condition("B20", "cond-hiv")],
        meds=[_med_statement("Tenofovir/Lamivudine/Dolutegravir", "med-tld")],
    )
    _monkeypatch_httpx(monkeypatch, transport)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await adjust_art_for_rif(ctx, {})

    assert result["status"] == "skipped"
    assert "rifampicin" in result["reason"].lower()


@pytest.mark.asyncio
async def test_proceeds_with_confirm_flag_even_no_rifampicin(monkeypatch):
    """Rifampicin about to be started: confirm flag allows adjustment anyway."""
    transport = _transport_factory(
        conditions=[_condition("B20", "cond-hiv")],
        meds=[_med_statement("Tenofovir/Lamivudine/Dolutegravir", "med-tld")],
    )
    _monkeypatch_httpx(monkeypatch, transport)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await adjust_art_for_rif(ctx, {"confirm_rifampicin_present": True})

    assert result["status"] == "ok"
    assert result["rifampicin_assumed_present"] is True
    assert result["detected_issue"]["id"] == "issue-1"
    assert result["new_prescription"]["id"] == "rx-1"


@pytest.mark.asyncio
async def test_full_path_hiv_dtg_and_rifampicin(monkeypatch):
    """The hero case: co-infected patient already on both drugs. Creates both resources."""
    transport = _transport_factory(
        conditions=[
            _condition("B20", "cond-hiv"),
            _condition("A15.0", "cond-tb"),
        ],
        meds=[
            _med_statement("Tenofovir/Lamivudine/Dolutegravir 300mg/300mg/50mg once daily", "med-tld"),
            _med_statement("Rifampicin/Isoniazid/Pyrazinamide/Ethambutol RHZE", "med-rhze"),
        ],
    )
    _monkeypatch_httpx(monkeypatch, transport)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await adjust_art_for_rif(ctx, {})

    assert result["status"] == "ok"
    assert result["dtg_medication_id"] == "med-tld"
    assert result["rifampicin_medication_id"] == "med-rhze"
    assert result["rifampicin_assumed_present"] is False
    assert result["detected_issue"]["severity"] == "moderate"
    assert result["continuation_weeks_post_rif"] == 2
    assert result["new_prescription"]["dosing"] == "BID (every 12 hours)"


@pytest.mark.asyncio
async def test_continuation_weeks_validation():
    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    with pytest.raises(ValueError, match="continuation_weeks_post_rif"):
        await adjust_art_for_rif(ctx, {"continuation_weeks_post_rif": 99})
