"""DaktariTB MCP tools.

Each tool is a callable with an MCP-style JSON schema. The registry maps
tool names to their implementations and declared schemas.
"""

from daktaritb_mcp.tools.base import ToolDefinition
from daktaritb_mcp.tools.order_tb_workup import order_tb_workup_tool

REGISTRY: dict[str, ToolDefinition] = {
    order_tb_workup_tool.name: order_tb_workup_tool,
}


def list_tools() -> list[dict]:
    """Return the tools/list response shape: [{name, description, inputSchema}]."""
    return [t.to_mcp_dict() for t in REGISTRY.values()]


def get_tool(name: str) -> ToolDefinition | None:
    return REGISTRY.get(name)
