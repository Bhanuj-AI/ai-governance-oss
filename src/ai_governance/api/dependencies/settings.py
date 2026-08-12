"""
REST API settings resolved from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiSettings:
    """
    Runtime settings for the REST control plane.
    """

    host: str
    environment: str
    port: int
    log_level: str
    log_format: str
    cors_allow_origins: tuple[str, ...]
    auto_seed_demo_data: bool
    tenancy_enabled: bool
    identity_provider: str
    auth_mode: str
    oidc_issuer: str | None
    oidc_jwks_refresh_seconds: int


def get_api_settings() -> ApiSettings:
    """
    Resolve REST API settings from environment variables.
    """

    environment = os.getenv("AI_GOVERNANCE_ENV", "local").strip().lower()
    identity_provider = os.getenv("AI_GOVERNANCE_AUTH_MODE", "development").strip().lower()
    allow_development_identity = os.getenv(
        "AI_GOVERNANCE_ALLOW_DEVELOPMENT_IDENTITY_IN_PRODUCTION", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    if (
        environment in {"production", "prod"}
        and identity_provider == "development"
        and not allow_development_identity
    ):
        raise ValueError(
            "The development identity provider is disabled in production. "
            "Set AI_GOVERNANCE_ALLOW_DEVELOPMENT_IDENTITY_IN_PRODUCTION=true only for an explicit exception."
        )
    return ApiSettings(
        host={"localhost": "127.0.0.1"}.get(
            os.getenv("AI_GOVERNANCE_API_HOST", "127.0.0.1"),
            os.getenv("AI_GOVERNANCE_API_HOST", "127.0.0.1"),
        ),
        environment=environment,
        port=int(os.getenv("AI_GOVERNANCE_API_PORT", "8000")),
        log_level=os.getenv("AI_GOVERNANCE_API_LOG_LEVEL", "info"),
        log_format=os.getenv("AI_GOVERNANCE_API_LOG_FORMAT", "json"),
        cors_allow_origins=_split_csv_env(
            "AI_GOVERNANCE_CORS_ALLOW_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ),
        auto_seed_demo_data=_auto_seed_demo_data_enabled(),
        tenancy_enabled=os.getenv("AI_GOVERNANCE_TENANCY_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "on"},
        identity_provider=identity_provider,
        auth_mode=os.getenv("AI_GOVERNANCE_AUTH_MODE", "development").strip().lower(),
        oidc_issuer=os.getenv("AI_GOVERNANCE_OIDC_ISSUER"),
        oidc_jwks_refresh_seconds=int(
            os.getenv("AI_GOVERNANCE_OIDC_JWKS_REFRESH_SECONDS", "300")
        ),
    )


def _split_csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        item.strip() for item in os.getenv(name, default).split(",") if item.strip()
    )


def _auto_seed_demo_data_enabled() -> bool:
    explicit = os.getenv("AI_GOVERNANCE_AUTO_SEED_DEMO_DATA")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}

    environment = os.getenv("AI_GOVERNANCE_ENV", "local").strip().lower()
    host = os.getenv("AI_GOVERNANCE_API_HOST", "127.0.0.1").strip().lower()
    return (
        "PYTEST_CURRENT_TEST" not in os.environ
        and environment in {"local", "dev", "development"}
        and host in {"127.0.0.1", "localhost", "0.0.0.0"}
    )
