"""FastAPI entrypoint for the DaktariTB MCP server.

Exposes:
  GET  /healthz  — liveness probe for deploy platforms
  POST /mcp      — JSON-RPC 2.0 endpoint per MCP spec

Run locally:
  uvicorn daktaritb_mcp.server:app --reload --port 8000
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from daktaritb_mcp import __version__
from daktaritb_mcp.config import settings
from daktaritb_mcp.mcp import initialize as mcp_initialize
from daktaritb_mcp.mcp.protocol import ErrorCode, JsonRpcRequest, fail, ok

logging.basicConfig(level=settings.log_level.upper())
log = logging.getLogger("daktaritb_mcp")

app = FastAPI(
    title="DaktariTB MCP",
    description="TB/HIV clinical action tools for Prompt Opinion",
    version=__version__,
)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Simple liveness probe. Used by DigitalOcean / load balancers."""
    return {"status": "ok", "service": "daktaritb-mcp", "version": __version__}


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """Handle MCP JSON-RPC 2.0 requests.

    Current methods supported:
      - initialize  : advertises capabilities (FHIR context extension)
      - tools/list  : returns [] for now; tools arrive in step 2
      - tools/call  : returns METHOD_NOT_FOUND until step 2

    Everything else returns a standard METHOD_NOT_FOUND error.
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

    # Parse into a JsonRpcRequest (handles validation).
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

    # Dispatch on method.
    if rpc.method == "initialize":
        params = rpc.params if isinstance(rpc.params, dict) else None
        result = mcp_initialize.handle_initialize(params)
        return JSONResponse(content=ok(rpc.id, result).model_dump(exclude_none=True))

    if rpc.method == "tools/list":
        # Empty for now — Step 2 fills this in with order_tb_workup etc.
        return JSONResponse(content=ok(rpc.id, {"tools": []}).model_dump(exclude_none=True))

    if rpc.method == "notifications/initialized":
        # MCP clients send this notification after initialize. No response needed
        # for notifications (no id), but return 200 with empty body.
        return JSONResponse(content={}, status_code=200)

    return JSONResponse(
        content=fail(rpc.id, ErrorCode.METHOD_NOT_FOUND, f"Method not found: {rpc.method}").model_dump(
            exclude_none=True
        ),
        status_code=200,  # JSON-RPC errors are 200 at HTTP level by convention
    )
