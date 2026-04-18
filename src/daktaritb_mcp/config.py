"""Configuration loaded from environment variables.

At runtime inside Prompt Opinion, patient-specific FHIR context arrives via
request headers (X-FHIR-Server-URL, X-FHIR-Access-Token, X-Patient-ID).
This config only holds server-level settings that don't change per request.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Optional dev/test FHIR endpoint (not used at runtime under Po)
    dev_fhir_base_url: str = ""
    dev_fhir_access_token: str = ""

    # Kenya MOH facility metadata (for TB-001 form)
    moh_facility_code: str = ""
    moh_facility_name: str = ""

    # Debug
    debug_log_requests: bool = False


settings = Settings()
