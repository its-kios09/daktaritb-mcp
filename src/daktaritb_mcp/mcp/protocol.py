"""JSON-RPC 2.0 request/response models used by MCP.

Reference: https://www.jsonrpc.org/specification
MCP layers on top of JSON-RPC 2.0: https://modelcontextprotocol.io/specification
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Standard JSON-RPC 2.0 error codes ---
class ErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | list[Any] | None = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: dict[str, Any] | None = None
    error: JsonRpcError | None = None


def ok(request_id: int | str | None, result: dict[str, Any]) -> JsonRpcResponse:
    """Build a successful JSON-RPC response."""
    return JsonRpcResponse(id=request_id, result=result)


def fail(
    request_id: int | str | None,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> JsonRpcResponse:
    """Build a JSON-RPC error response."""
    return JsonRpcResponse(
        id=request_id,
        error=JsonRpcError(code=code, message=message, data=data),
    )
