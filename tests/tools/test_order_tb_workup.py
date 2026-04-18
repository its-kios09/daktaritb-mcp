"""Tests for the order_tb_workup tool.

We mock the FHIR server with httpx's MockTransport so we don't need a real
FHIR instance to test clinical logic. Tests focus on: order composition,
LF-LAM inclusion rules, reasonReference wiring, error handling.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from daktaritb_mcp.fhir.context import FhirContext, MissingFhirContext
from daktaritb_mcp.tools.order_tb_workup import run as order_tb_workup

FHIR_BASE = "https://fhir.example.com"
PATIENT_ID = "patient-wanjiru"


def _condition(code: str, display: str, cid: str) -> dict[str, Any]:
    return {
        "resourceType": "Condition",
        "id": cid,
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]
        },
        "code": {
            "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": code, "display": display}],
            "text": display,
        },
        "subject": {"reference": f"Patient/{PATIENT_ID}"},
    }


def _cd4_obs(value: float) -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "id": "obs-cd4",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "24467-3", "display": "CD4+ T cells"}]},
        "subject": {"reference": f"Patient/{PATIENT_ID}"},
        "valueQuantity": {"value": value, "unit": "cells/uL"},
    }


def _bundle(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"resourceType": "Bundle", "type": "searchset", "entry": [{"resource": r} for r in entries]}


def _make_mock_transport(
    conditions: list[dict[str, Any]],
    cd4_value: float | None,
    post_responses: list[dict[str, Any]] | None = None,
) -> httpx.MockTransport:
    """Build an httpx MockTransport that mimics a FHIR server."""
    created_responses = iter(post_responses or [])

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        method = request.method

        if method == "GET" and "/Condition" in url:
            return httpx.Response(200, json=_bundle(conditions))
        if method == "GET" and "/Observation" in url:
            obs = [_cd4_obs(cd4_value)] if cd4_value is not None else []
            return httpx.Response(200, json=_bundle(obs))
        if method == "POST" and "/ServiceRequest" in url:
            try:
                preset = next(created_responses)
            except StopIteration:
                # Default: echo back with a generated id
                resource = request.content.decode()
                import json as _json
                parsed = _json.loads(resource)
                parsed["id"] = f"sr-{len(preset if False else 'new')}"
                return httpx.Response(201, json=parsed)
            return httpx.Response(201, json=preset)

        return httpx.Response(404, json={"resourceType": "OperationOutcome"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_requires_patient_context():
    ctx = FhirContext(server_url=FHIR_BASE, access_token=None, patient_id=None)
    with pytest.raises(MissingFhirContext):
        await order_tb_workup(ctx, {})


@pytest.mark.asyncio
async def test_hiv_negative_no_lf_lam(monkeypatch):
    """Non-HIV patient: no LF-LAM even with low CD4."""
    conditions: list[dict[str, Any]] = []  # no HIV
    transport = _make_mock_transport(conditions, cd4_value=None)

    original_client = httpx.AsyncClient

    class _Patched(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("daktaritb_mcp.fhir.client.httpx.AsyncClient", _Patched)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await order_tb_workup(ctx, {})

    assert result["hiv_positive"] is False
    assert result["lf_lam_included"] is False
    # 3 orders: GeneXpert, AFB, CXR
    assert len(result["orders_created"]) == 3
    codes = [o["code"] for o in result["orders_created"]]
    assert "88142-3" in codes  # GeneXpert
    assert "648-0" in codes    # AFB
    assert "36554-4" in codes  # CXR
    assert "95745-4" not in codes  # no LF-LAM


@pytest.mark.asyncio
async def test_hiv_positive_low_cd4_includes_lf_lam(monkeypatch):
    """HIV+ with CD4 < 350: LF-LAM is added."""
    conditions = [_condition("B20", "HIV disease", "cond-hiv")]
    transport = _make_mock_transport(conditions, cd4_value=290.0)

    original_client = httpx.AsyncClient

    class _Patched(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("daktaritb_mcp.fhir.client.httpx.AsyncClient", _Patched)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await order_tb_workup(ctx, {})

    assert result["hiv_positive"] is True
    assert result["latest_cd4"] == 290.0
    assert result["lf_lam_included"] is True
    assert "Condition/cond-hiv" in result["reason_references"]
    codes = [o["code"] for o in result["orders_created"]]
    assert "95745-4" in codes  # LF-LAM added


@pytest.mark.asyncio
async def test_hiv_positive_high_cd4_skips_lf_lam(monkeypatch):
    """HIV+ with CD4 >= 350: LF-LAM is NOT added (not clinically useful)."""
    conditions = [_condition("B20", "HIV disease", "cond-hiv")]
    transport = _make_mock_transport(conditions, cd4_value=720.0)

    original_client = httpx.AsyncClient

    class _Patched(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("daktaritb_mcp.fhir.client.httpx.AsyncClient", _Patched)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await order_tb_workup(ctx, {})

    assert result["hiv_positive"] is True
    assert result["lf_lam_included"] is False


@pytest.mark.asyncio
async def test_urgency_validation():
    """Invalid urgency arg raises ValueError."""
    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    with pytest.raises(ValueError, match="Invalid urgency"):
        await order_tb_workup(ctx, {"urgency": "bogus"})


@pytest.mark.asyncio
async def test_skip_afb_and_cxr(monkeypatch):
    """Flags let clinician opt out of AFB or CXR."""
    transport = _make_mock_transport(conditions=[], cd4_value=None)
    original_client = httpx.AsyncClient

    class _Patched(original_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("daktaritb_mcp.fhir.client.httpx.AsyncClient", _Patched)

    ctx = FhirContext(server_url=FHIR_BASE, access_token="t", patient_id=PATIENT_ID)
    result = await order_tb_workup(
        ctx,
        {"include_afb_smear": False, "include_chest_xray": False},
    )
    codes = [o["code"] for o in result["orders_created"]]
    assert codes == ["88142-3"]  # GeneXpert only
