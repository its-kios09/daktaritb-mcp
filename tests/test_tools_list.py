"""Integration: tools/list now returns order_tb_workup."""

from fastapi.testclient import TestClient

from daktaritb_mcp.server import app

client = TestClient(app)


def test_tools_list_returns_order_tb_workup():
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    body = response.json()
    tools = body["result"]["tools"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == "order_tb_workup"
    assert "ServiceRequest" in tool["description"]
    assert "urgency" in tool["inputSchema"]["properties"]
