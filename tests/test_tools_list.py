"""Integration: tools/list returns all 3 tools."""

from fastapi.testclient import TestClient

from daktaritb_mcp.server import app

client = TestClient(app)


def test_tools_list_returns_all_tools():
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    body = response.json()
    tools = body["result"]["tools"]
    names = {t["name"] for t in tools}

    assert "order_tb_workup" in names
    assert "adjust_art_for_rif" in names
    assert "generate_tb_notification" in names

    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
