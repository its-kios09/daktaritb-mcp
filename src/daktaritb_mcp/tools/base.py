"""Base class for MCP tools.

A ToolDefinition bundles the declaration (name, description, JSON schema for
inputs) with the async function that implements the tool. MCP's tools/list
needs the declaration; tools/call dispatches to the implementation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from daktaritb_mcp.fhir.context import FhirContext

# A tool implementation takes (ctx, arguments) and returns a result dict.
ToolImpl = Callable[[FhirContext, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class ToolDefinition:
    """An MCP tool: metadata + implementation."""

    name: str
    description: str
    input_schema: dict[str, Any]
    impl: ToolImpl
    # Whether this tool requires a patient in the FHIR context.
    requires_patient: bool = True
    # Additional metadata surfaced to the client.
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_mcp_dict(self) -> dict[str, Any]:
        """Shape for tools/list response."""
        d: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.annotations:
            d["annotations"] = self.annotations
        return d
