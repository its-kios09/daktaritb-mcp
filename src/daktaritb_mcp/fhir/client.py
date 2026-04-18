"""Async FHIR R4 HTTP client.

Thin wrapper around httpx that knows how to:
- Search resources with query params
- Fetch a resource by id
- Create a resource (POST) and return the server-assigned id

We intentionally keep this small and focused — it's NOT a full FHIR SDK.
"""

from __future__ import annotations

from typing import Any

import httpx

from daktaritb_mcp.fhir.context import FhirContext


class FhirError(Exception):
    """Raised when a FHIR request fails."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class FhirClient:
    """Async FHIR client bound to a single FhirContext (one tool invocation)."""

    def __init__(self, ctx: FhirContext, timeout: float = 30.0):
        self.ctx = ctx
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
        if self.ctx.access_token:
            headers["Authorization"] = f"Bearer {self.ctx.access_token}"
        return headers

    async def search(self, resource_type: str, params: dict[str, str]) -> dict[str, Any]:
        """Run a FHIR search, e.g. search('Observation', {'patient': 'abc', 'code': '24467-3'}).

        Returns the FHIR Bundle as a dict. Caller walks bundle.entry.
        """
        url = f"{self.ctx.server_url}/{resource_type}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.get(url, headers=self._headers(), params=params)
            except httpx.HTTPError as e:
                raise FhirError(f"FHIR search failed: {e}") from e
        if resp.status_code >= 400:
            raise FhirError(
                f"FHIR search {resource_type} returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        return resp.json()

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """Read a single resource by id. Returns the resource dict."""
        url = f"{self.ctx.server_url}/{resource_type}/{resource_id}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.get(url, headers=self._headers())
            except httpx.HTTPError as e:
                raise FhirError(f"FHIR read failed: {e}") from e
        if resp.status_code >= 400:
            raise FhirError(
                f"FHIR read {resource_type}/{resource_id} returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        return resp.json()

    async def create(self, resource: dict[str, Any]) -> dict[str, Any]:
        """POST a resource to the FHIR server. Returns the created resource
        (now with server-assigned id + meta)."""
        resource_type = resource.get("resourceType")
        if not resource_type:
            raise FhirError("Cannot create resource without resourceType")
        url = f"{self.ctx.server_url}/{resource_type}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(url, headers=self._headers(), json=resource)
            except httpx.HTTPError as e:
                raise FhirError(f"FHIR create failed: {e}") from e
        if resp.status_code not in (200, 201):
            raise FhirError(
                f"FHIR create {resource_type} returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        return resp.json()

    @staticmethod
    def extract_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
        """Walk a FHIR search Bundle and return [resource, ...] from its entries."""
        return [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
