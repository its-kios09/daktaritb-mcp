"""DaktariTB MCP tools."""

from daktaritb_mcp.tools.adjust_art_for_rif import adjust_art_for_rif_tool
from daktaritb_mcp.tools.base import ToolDefinition
from daktaritb_mcp.tools.generate_tb_notification import generate_tb_notification_tool
from daktaritb_mcp.tools.order_tb_workup import order_tb_workup_tool

REGISTRY: dict[str, ToolDefinition] = {
    order_tb_workup_tool.name: order_tb_workup_tool,
    adjust_art_for_rif_tool.name: adjust_art_for_rif_tool,
    generate_tb_notification_tool.name: generate_tb_notification_tool,
}


def list_tools() -> list[dict]:
    return [t.to_mcp_dict() for t in REGISTRY.values()]


def get_tool(name: str) -> ToolDefinition | None:
    return REGISTRY.get(name)
