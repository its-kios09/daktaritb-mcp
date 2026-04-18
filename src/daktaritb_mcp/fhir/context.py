"""Read Prompt Opinion SHARP context from request headers.

Per https://docs.promptopinion.ai/fhir-context/mcp-fhir-context, Po sends
three headers when invoking a tool on a server that declares the FHIR
context extension:

    X-FHIR-Server-URL    — base URL of the FHIR server
    X-FHIR-Access-Token  — optional; some FHIR servers require it
    X-Patient-ID         — present only in patient-scoped calls

Header names are case-insensitive per RFC 7230; HTTP/2 actually lowercases
them on the wire. FastAPI's `Headers` is case-insensitive so we can use
either form in code.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class FhirContext:
    """Immutable FHIR context for the lifetime of a single tool invocation."""

    server_url: str
    access_token: str | None
    patient_id: str | None

    @property
    def has_patient(self) -> bool:
        return bool(self.patient_id)


class MissingFhirContext(Exception):
    """Raised when a tool that requires FHIR context is called without it."""


def extract_context(request: Request) -> FhirContext:
    """Pull SHARP headers out of the FastAPI request.

    We do NOT enforce patient_id here — some tools work at workspace scope.
    Individual tools that require a patient raise MissingFhirContext themselves.
    """
    server_url = request.headers.get("X-FHIR-Server-URL", "").strip()
    if not server_url:
        # No server URL at all = no FHIR context was passed. The tool
        # probably can't do its job, but let the tool decide.
        return FhirContext(server_url="", access_token=None, patient_id=None)

    access_token = request.headers.get("X-FHIR-Access-Token", "").strip() or None
    patient_id = request.headers.get("X-Patient-ID", "").strip() or None

    return FhirContext(
        server_url=server_url.rstrip("/"),
        access_token=access_token,
        patient_id=patient_id,
    )
