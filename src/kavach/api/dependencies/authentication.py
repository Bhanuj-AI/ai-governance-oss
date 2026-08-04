"""
FastAPI authentication dependency for Keycloak OIDC.

Provides ``get_authenticated_principal`` which extracts the Bearer token
from the ``Authorization`` header, validates it against Keycloak, and
returns an ``AuthenticatedPrincipal``.

In development mode the existing header-based behaviour is preserved.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import Header, HTTPException, Request, status

from kavach.api.dependencies.settings import get_api_settings
from kavach.tenancy.authentication import (
    AuthenticationError,
    AuthenticationService,
)
from kavach.tenancy.domain import AuthenticatedPrincipal

logger = logging.getLogger("kavach.api.authentication")


@lru_cache(maxsize=8)
def get_authentication_service(
    audience: str | None = None,
) -> AuthenticationService:
    """Create the shared authentication service instance."""
    settings = get_api_settings()
    auth_mode = settings.auth_mode

    if auth_mode != "keycloak":
        return AuthenticationService(
            issuer="http://localhost:8080/realms/kavach",
            jwks_refresh_seconds=300,
        )

    oidc_issuer = settings.oidc_issuer
    if not oidc_issuer:
        raise ValueError(
            "KAVACH_OIDC_ISSUER is required when KAVACH_AUTH_MODE=keycloak"
        )

    return AuthenticationService(
        issuer=oidc_issuer,
        jwks_refresh_seconds=settings.oidc_jwks_refresh_seconds,
        audience=audience,
    )


def get_authenticated_principal(
    authorization: str | None = Header(default=None, alias="Authorization"),
    request: Request = None,  # type: ignore[assignment]
) -> AuthenticatedPrincipal:
    """
    FastAPI dependency that validates the Bearer JWT and returns the principal.

    Development mode
    ----------------
    When ``KAVACH_AUTH_MODE=development`` the existing behaviour is preserved:
    the actor identity comes from ``X-Kavach-Actor-Id`` header or the
    ``KAVACH_DEVELOPMENT_ACTOR_ID`` environment variable. No JWT validation
    occurs.

    Keycloak mode
    -------------
    When ``KAVACH_AUTH_MODE=keycloak`` the ``Authorization: Bearer <token>``
    header is required. Missing or invalid tokens return HTTP 401.
    """
    settings = get_api_settings()
    auth_mode = settings.auth_mode

    if auth_mode == "development":
        # Preserve existing development behaviour — no JWT validation.
        # The actor identity is resolved downstream in get_tenant_context.
        # Return a sentinel principal so downstream code can proceed.
        return _development_principal()

    # Keycloak mode — JWT required
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "missing_authorization",
                    "message": "Authorization header is required",
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "invalid_authorization",
                    "message": "Authorization must use Bearer scheme",
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    service = get_authentication_service()

    try:
        return service.validate(token)
    except AuthenticationError as exc:
        logger.warning(
            "jwt_validation_failed: %s",
            str(exc),
            extra={"code": exc.code, "error_message": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


def _development_principal() -> AuthenticatedPrincipal:
    """
    Create a development-mode principal from environment / headers.

    This preserves the existing development behaviour where the actor
    identity comes from ``X-Kavach-Actor-Id`` or
    ``KAVACH_DEVELOPMENT_ACTOR_ID``.
    """
    import os

    actor_id = os.getenv("KAVACH_DEVELOPMENT_ACTOR_ID")
    from kavach.tenancy.domain import ActorType

    return AuthenticatedPrincipal(
        subject=actor_id,
        principal_type=ActorType.SYSTEM,
        organization_id=None,
        client_id="development",
        issuer="development",
    )
