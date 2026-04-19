"""FastAPI entrypoint for the DaktariTB MCP server.

Exposes:
  GET  /healthz  — liveness probe for deploy platforms
  POST /mcp      — JSON-RPC 2.0 endpoint per MCP spec

Run locally:
  uvicorn daktaritb_mcp.server:app --reload --port 8000
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from daktaritb_mcp import __version__
from daktaritb_mcp.config import settings
from daktaritb_mcp.fhir.context import MissingFhirContext, extract_context
from daktaritb_mcp.mcp import initialize as mcp_initialize
from daktaritb_mcp.mcp.protocol import ErrorCode, JsonRpcRequest, fail, ok
from daktaritb_mcp.tools import get_tool, list_tools

logging.basicConfig(level=settings.log_level.upper())
log = logging.getLogger("daktaritb_mcp")

app = FastAPI(
    title="DaktariTB MCP",
    description="TB/HIV clinical action tools for Prompt Opinion",
    version=__version__,
)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Simple liveness probe."""
    return {"status": "ok", "service": "daktaritb-mcp", "version": __version__}


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """Handle MCP JSON-RPC 2.0 requests.

    Methods:
      - initialize              : advertise FHIR context capability
      - notifications/initialized: ack (no response)
      - tools/list              : return declared tools
      - tools/call              : dispatch to tool implementation
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content=fail(None, ErrorCode.PARSE_ERROR, "Malformed JSON").model_dump(
                exclude_none=True
            ),
            status_code=400,
        )

    try:
        rpc = JsonRpcRequest.model_validate(body)
    except Exception as e:
        return JSONResponse(
            content=fail(
                body.get("id") if isinstance(body, dict) else None,
                ErrorCode.INVALID_REQUEST,
                f"Invalid JSON-RPC request: {e}",
            ).model_dump(exclude_none=True),
            status_code=400,
        )

    if settings.debug_log_requests:
        log.info("MCP method=%s id=%s", rpc.method, rpc.id)

    # --- initialize ---
    if rpc.method == "initialize":
        params = rpc.params if isinstance(rpc.params, dict) else None
        result = mcp_initialize.handle_initialize(params)
        return JSONResponse(content=ok(rpc.id, result).model_dump(exclude_none=True))

    # --- initialized notification (no response body, but must 200) ---
    if rpc.method == "notifications/initialized":
        return JSONResponse(content={}, status_code=200)

    # --- tools/list ---
    if rpc.method == "tools/list":
        return JSONResponse(
            content=ok(rpc.id, {"tools": list_tools()}).model_dump(exclude_none=True)
        )

    # --- tools/call ---
    if rpc.method == "tools/call":
        params = rpc.params if isinstance(rpc.params, dict) else {}
        tool_name = params.get("name")
        arguments = params.get("arguments", {}) or {}

        tool = get_tool(tool_name) if tool_name else None
        if not tool:
            return JSONResponse(
                content=fail(
                    rpc.id,
                    ErrorCode.INVALID_PARAMS,
                    f"Unknown tool: {tool_name}",
                ).model_dump(exclude_none=True)
            )

        ctx = extract_context(request)

        try:
            result = await tool.impl(ctx, arguments)
        except MissingFhirContext as e:
            return JSONResponse(
                content=fail(rpc.id, ErrorCode.INVALID_PARAMS, str(e)).model_dump(
                    exclude_none=True
                )
            )
        except ValueError as e:
            return JSONResponse(
                content=fail(rpc.id, ErrorCode.INVALID_PARAMS, str(e)).model_dump(
                    exclude_none=True
                )
            )
        except Exception as e:
            log.error("tools/call %s failed: %s\n%s", tool_name, e, traceback.format_exc())
            return JSONResponse(
                content=fail(
                    rpc.id,
                    ErrorCode.INTERNAL_ERROR,
                    f"Tool execution failed: {e}",
                ).model_dump(exclude_none=True)
            )

        # MCP tools/call response shape: content as array of content parts.
        return JSONResponse(
            content=ok(
                rpc.id,
                {
                    "content": [
                        {"type": "text", "text": _summarize_for_humans(tool_name, result)},
                    ],
                    "structuredContent": result,
                    "isError": False,
                },
            ).model_dump(exclude_none=True)
        )

    return JSONResponse(
        content=fail(rpc.id, ErrorCode.METHOD_NOT_FOUND, f"Method not found: {rpc.method}").model_dump(
            exclude_none=True
        ),
        status_code=200,
    )


def _summarize_for_humans(tool_name: str, result: dict[str, Any]) -> str:
    """Short natural-language summary shown in chat UI alongside structured output."""
    if tool_name == "order_tb_workup":
        return result.get("summary", "TB workup orders placed.")
    if tool_name == "adjust_art_for_rif":
        status = result.get("status", "")
        if status == "skipped":
            return result.get("reason", "No ART adjustment needed.")
        if status == "error":
            return f"ART adjustment failed at step {result.get('step_failed', 'unknown')}."
        return result.get("summary", "ART regimen adjusted for rifampicin.")
    return f"Tool {tool_name} completed."


def run() -> None:
    """Entrypoint for `python -m daktaritb_mcp.server`."""
    import os

    import uvicorn

    port = int(os.environ.get("PORT", settings.port))
    uvicorn.run(
        "daktaritb_mcp.server:app",
        host=settings.host,
        port=port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    run()
