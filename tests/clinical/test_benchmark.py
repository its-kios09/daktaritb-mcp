"""Clinical benchmark runner.

Running this file with pytest executes all 10 scenarios and asserts
each scenario's expected_assertions hold.

For the markdown report, run scripts/run_clinical_benchmark.py instead.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from daktaritb_mcp.fhir.context import FhirContext
from daktaritb_mcp.tools import get_tool
from tests.clinical.fixtures import bundle
from tests.clinical.scenarios import ALL_SCENARIOS, Scenario


def _build_transport(scenario: Scenario) -> httpx.MockTransport:
    """Build an httpx MockTransport that serves scenario's FHIR fixtures."""
    patient_res = scenario.patient_builder()
    patient_id = patient_res["id"]
    counter = {"docref": 0, "issue": 0, "rx": 0, "servicereq": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        method = request.method

        # Patient read
        if method == "GET" and f"/Patient/{patient_id}" in url and "?" not in url.split("/Patient/")[-1]:
            return httpx.Response(200, json=patient_res)

        if method == "GET" and "/Condition" in url:
            return httpx.Response(200, json=bundle(scenario.conditions))

        if method == "GET" and "/MedicationStatement" in url:
            return httpx.Response(200, json=bundle(scenario.medications))

        if method == "GET" and "/Observation" in url:
            params = dict(request.url.params)
            code = params.get("code", "")
            obs = scenario.observations.get(code, [])
            return httpx.Response(200, json=bundle(obs))

        if method == "POST":
            body = json.loads(request.content) if request.content else {}
            if "/ServiceRequest" in url:
                counter["servicereq"] += 1
                body["id"] = f"sr-{counter['servicereq']}"
                return httpx.Response(201, json=body)
            if "/DetectedIssue" in url:
                counter["issue"] += 1
                body["id"] = f"di-{counter['issue']}"
                return httpx.Response(201, json=body)
            if "/MedicationRequest" in url:
                counter["rx"] += 1
                body["id"] = f"mr-{counter['rx']}"
                return httpx.Response(201, json=body)
            if "/DocumentReference" in url:
                counter["docref"] += 1
                body["id"] = f"dr-{counter['docref']}"
                return httpx.Response(201, json=body)

        return httpx.Response(404, json={"resourceType": "OperationOutcome"})

    return httpx.MockTransport(handler)


@pytest.fixture
def monkeypatch_httpx_for(monkeypatch):
    """Returns a function that installs the mock transport for a scenario."""

    def _install(scenario: Scenario):
        transport = _build_transport(scenario)
        original = httpx.AsyncClient

        class _Patched(original):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        monkeypatch.setattr("daktaritb_mcp.fhir.client.httpx.AsyncClient", _Patched)

    return _install


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=[f"S{s.id:02d}-{s.name}" for s in ALL_SCENARIOS])
async def test_scenario(scenario: Scenario, monkeypatch_httpx_for):
    """Run a single benchmark scenario."""
    monkeypatch_httpx_for(scenario)

    tool = get_tool(scenario.tool)
    assert tool is not None, f"Tool {scenario.tool} not registered"

    patient_id = scenario.patient_builder()["id"]
    ctx = FhirContext(
        server_url="https://fhir.example.com",
        access_token="bench-token",
        patient_id=patient_id,
    )

    result = await tool.impl(ctx, scenario.tool_arguments)

    # Some tools (order_tb_workup) return success implicitly via errors=[]
    # rather than an explicit status field. Normalize for the assertion.
    actual_status = result.get("status")
    if actual_status is None and "errors" in result:
        actual_status = "ok" if not result["errors"] else "error"

    # Top-level status check first (fail-fast with useful message)
    assert actual_status == scenario.expected_status, (
        f"Scenario {scenario.id} ({scenario.name}): "
        f"expected status={scenario.expected_status}, got {actual_status}. "
        f"Full result: {json.dumps(result, indent=2, default=str)}"
    )

    # Per-assertion checks
    for i, assertion in enumerate(scenario.expected_assertions):
        assert assertion(result), (
            f"Scenario {scenario.id} assertion #{i + 1} failed.\n"
            f"Guideline: {scenario.guideline_citation}\n"
            f"Result: {json.dumps(result, indent=2, default=str)}"
        )
