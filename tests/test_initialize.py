"""Tests for the MCP initialize handler.

These tests verify the critical capability declaration that tells Prompt
Opinion we support the FHIR context extension. If this test fails, the
Po UI won't show the 'trust FHIR context' prompt at registration.
"""

from fastapi.testclient import TestClient

from daktaritb_mcp.server import app

client = TestClient(app)


def test_healthz():
    """Liveness probe should always return ok."""
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "daktaritb-mcp"


def test_initialize_declares_fhir_context_extension():
    """The initialize response MUST declare ai.promptopinion/fhir-context.

    This is the hard requirement for Prompt Opinion to trust our server with
    patient FHIR context. Breaking this test = breaking integration.
    """
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "0.0.1"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert "result" in body
    assert "error" not in body or body.get("error") is None

    result = body["result"]
    assert "capabilities" in result
    assert "extensions" in result["capabilities"]
    assert "ai.promptopinion/fhir-context" in result["capabilities"]["extensions"]
    assert result["serverInfo"]["name"] == "daktaritb-mcp"


def test_tools_list_returns_empty_for_now():
    """tools/list should return an empty list in Step 1b.

    Step 2 will populate this with order_tb_workup, adjust_art_for_rif, etc.
    """
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == {"tools": []}


def test_unknown_method_returns_method_not_found():
    """Any method we don't implement should return -32601."""
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "does/not/exist"},
    )
    body = response.json()
    assert body["error"]["code"] == -32601


def test_malformed_json_returns_parse_error():
    """Invalid JSON body should return -32700."""
    response = client.post(
        "/mcp",
        content=b"{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == -32700
