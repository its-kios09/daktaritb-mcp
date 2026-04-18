"""MCP `initialize` handler.

This is the single most important handler in our server for Prompt Opinion
integration. When Po registers our server, it sends an `initialize` request
and reads the `capabilities.extensions` to determine what we support.

By declaring `ai.promptopinion/fhir-context`, we tell Po:
  "We know how to read the X-FHIR-Server-URL, X-FHIR-Access-Token,
   and X-Patient-ID headers you'll send us — trust us with FHIR context."

The user is then prompted in the Po UI to authorize this trust.

Spec: https://docs.promptopinion.ai/fhir-context/mcp-fhir-context
"""

from __future__ import annotations

from typing import Any

# Protocol version we implement. MCP uses dated revisions.
MCP_PROTOCOL_VERSION = "2024-11-05"

# Server identity returned to the client.
SERVER_INFO = {
    "name": "daktaritb-mcp",
    "version": "0.1.0",
}

# Capabilities declaration.
# - `tools: {}` means "we expose tools" (list returned via tools/list).
# - `extensions` is where we advertise Po's FHIR context support.
CAPABILITIES = {
    "tools": {},
    "extensions": {
        "ai.promptopinion/fhir-context": {},
    },
}


def handle_initialize(params: dict[str, Any] | None) -> dict[str, Any]:
    """Return the initialize response payload.

    Per MCP spec, we don't strictly need to inspect the client's params to
    respond — but in a real server we might negotiate protocol version or
    capabilities. For v1 we return a fixed response.
    """
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": CAPABILITIES,
        "serverInfo": SERVER_INFO,
    }
