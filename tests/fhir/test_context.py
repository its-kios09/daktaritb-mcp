"""Tests for SHARP header extraction."""

from fastapi import Request
from fastapi.testclient import TestClient

from daktaritb_mcp.fhir.context import extract_context
from daktaritb_mcp.server import app


def test_extract_context_with_all_headers():
    """A patient-scoped call should yield a full context."""
    from fastapi import FastAPI

    captured = {}

    probe = FastAPI()

    @probe.post("/probe")
    async def probe_endpoint(request: Request):
        captured["ctx"] = extract_context(request)
        return {"ok": True}

    client = TestClient(probe)
    client.post(
        "/probe",
        headers={
            "X-FHIR-Server-URL": "https://fhir.example.com/",
            "X-FHIR-Access-Token": "token-xyz",
            "X-Patient-ID": "patient-123",
        },
    )
    ctx = captured["ctx"]
    assert ctx.server_url == "https://fhir.example.com"  # trailing slash stripped
    assert ctx.access_token == "token-xyz"
    assert ctx.patient_id == "patient-123"
    assert ctx.has_patient is True


def test_extract_context_without_patient():
    """Workspace-scoped calls have no patient id."""
    from fastapi import FastAPI

    captured = {}
    probe = FastAPI()

    @probe.post("/probe")
    async def probe_endpoint(request: Request):
        captured["ctx"] = extract_context(request)
        return {"ok": True}

    client = TestClient(probe)
    client.post(
        "/probe",
        headers={"X-FHIR-Server-URL": "https://fhir.example.com"},
    )
    assert captured["ctx"].has_patient is False


def test_extract_context_empty():
    """No headers at all yields an empty context."""
    from fastapi import FastAPI

    captured = {}
    probe = FastAPI()

    @probe.post("/probe")
    async def probe_endpoint(request: Request):
        captured["ctx"] = extract_context(request)
        return {"ok": True}

    client = TestClient(probe)
    client.post("/probe")
    ctx = captured["ctx"]
    assert ctx.server_url == ""
    assert ctx.access_token is None
    assert ctx.patient_id is None
