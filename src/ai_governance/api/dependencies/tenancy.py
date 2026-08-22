from __future__ import annotations

import os
from functools import lru_cache
from uuid import uuid4

from fastapi import Depends, Header  # type: ignore

from ai_governance.api.dependencies.authentication import (
    get_authenticated_principal,
)
from ai_governance.tenancy.authorization import AuthorizationService
from ai_governance.tenancy.context_factory import TenantContextFactory
from ai_governance.tenancy.domain import AuthenticatedPrincipal, TenantContext
from ai_governance.tenancy.errors import (
    OrganizationNotFound,
    ProjectNotFound,
    TenantContextInvalid,
    TenantContextMissing,
    TenantScopeMismatch,
)
from ai_governance.tenancy.observability import METRICS
from ai_governance.tenancy.repository import InMemoryControlPlaneRepository
from ai_governance.tenancy.services import (
    ControlPlaneService,
    bootstrap_control_plane,
    provision_mcp_service_account,
    provision_walkthrough_service_account,
)


@lru_cache(maxsize=1)
def get_control_plane_repository():
    backend = os.getenv("AI_GOVERNANCE_TENANCY_REPOSITORY", "inmemory").strip().lower()
    if backend == "inmemory":
        repository = InMemoryControlPlaneRepository()
    elif backend == "sqlite":
        from ai_governance.repositories.factories.sqlite_database import (
            create_sqlite_database,
        )
        from ai_governance.tenancy.sqlite_repository import SQLiteControlPlaneRepository

        path = os.getenv("AI_GOVERNANCE_TENANCY_SQLITE_PATH")
        if not path:
            raise ValueError(
                "AI_GOVERNANCE_TENANCY_SQLITE_PATH is required when "
                "AI_GOVERNANCE_TENANCY_REPOSITORY=sqlite"
            )
        repository = SQLiteControlPlaneRepository(create_sqlite_database(path))
    elif backend == "postgres":
        from ai_governance.tenancy.postgres_repository import (
            PostgresControlPlaneRepository,
        )

        dsn = os.getenv("AI_GOVERNANCE_TENANCY_POSTGRES_DSN")
        if not dsn:
            raise ValueError(
                "AI_GOVERNANCE_TENANCY_POSTGRES_DSN is required when "
                "AI_GOVERNANCE_TENANCY_REPOSITORY=postgres"
            )
        repository = PostgresControlPlaneRepository(dsn)
    else:
        raise ValueError(f"Unsupported tenancy repository backend: {backend}")
    bootstrap_control_plane(
        repository,
        organization_id=os.getenv("AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID", "org_default"),
        organization_name=os.getenv(
            "AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_NAME", "Default Organization"
        ),
        organization_slug=os.getenv("AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_SLUG", "default"),
        project_id=os.getenv("AI_GOVERNANCE_BOOTSTRAP_PROJECT_ID", "project_default"),
        project_name=os.getenv("AI_GOVERNANCE_BOOTSTRAP_PROJECT_NAME", "Default Project"),
        project_slug=os.getenv("AI_GOVERNANCE_BOOTSTRAP_PROJECT_SLUG", "default"),
        auth_mode=os.getenv("AI_GOVERNANCE_AUTH_MODE", "development").strip().lower(),
    )
    provision_mcp_service_account(
        repository,
        organization_id=os.getenv("AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID", "org_default"),
    )
    provision_walkthrough_service_account(
        repository,
        organization_id=os.getenv("AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID", "org_default"),
    )
    return repository


@lru_cache(maxsize=1)
def get_authorization_service() -> AuthorizationService:
    return AuthorizationService(get_control_plane_repository())


@lru_cache(maxsize=1)
def get_control_plane_service() -> ControlPlaneService:
    return ControlPlaneService(
        get_control_plane_repository(), get_authorization_service()
    )


def _resolve_tenant_context_development(
    x_organization_id: str | None = Header(
        default=None, alias="X-AI-Governance-Organization-Id"
    ),
    x_project_id: str | None = Header(default=None, alias="X-AI-Governance-Project-Id"),
    x_actor_id: str | None = Header(default=None, alias="X-AI-Governance-Actor-Id"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
) -> TenantContext:
    """Resolve TenantContext using header-based development mode."""
    organization_id, project_id, actor_id = x_organization_id, x_project_id, x_actor_id
    if not organization_id:
        METRICS.record_context_resolution("missing")
        raise TenantContextMissing("X-AI-Governance-Organization-Id is required")
    provider = os.getenv("AI_GOVERNANCE_AUTH_MODE", "development").strip().lower()
    if provider == "development":
        actor_id = actor_id or os.getenv("AI_GOVERNANCE_DEVELOPMENT_ACTOR_ID", "local-admin")
    elif actor_id:
        raise TenantContextInvalid(
            "actor headers are only accepted by the development identity provider"
        )
    if not actor_id:
        raise TenantContextMissing("resolved actor identity is required")
    repository = get_control_plane_repository()
    try:
        repository.get_organization(organization_id)
    except OrganizationNotFound as exc:
        METRICS.record_context_resolution("invalid_organization")
        raise TenantContextInvalid("selected organization is invalid") from exc
    if project_id:
        try:
            repository.get_project(organization_id, project_id)
        except ProjectNotFound as exc:
            METRICS.record_context_resolution("scope_mismatch")
            raise TenantScopeMismatch(
                "selected project does not belong to the selected organization"
            ) from exc
    METRICS.record_context_resolution("resolved")
    return TenantContext(
        organization_id,
        project_id,
        actor_id,
        x_request_id or f"req_{uuid4().hex}",
        x_correlation_id,
    )


def get_tenant_context(
    x_organization_id: str | None = Header(
        default=None, alias="X-AI-Governance-Organization-Id"
    ),
    x_project_id: str | None = Header(default=None, alias="X-AI-Governance-Project-Id"),
    x_actor_id: str | None = Header(default=None, alias="X-AI-Governance-Actor-Id"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
) -> TenantContext:
    """
    Resolve TenantContext using the configured authentication mode.

    Development mode
    ----------------
    Uses header-based identity resolution (existing behaviour).

    Keycloak mode
    -------------
    Derives actor identity from the validated JWT principal.
    Organization scope must come from the JWT claim or be provided via
    ``X-AI-Governance-Organization-Id`` header.
    """
    auth_mode = os.getenv("AI_GOVERNANCE_AUTH_MODE", "development").strip().lower()

    if auth_mode == "development":
        return _resolve_tenant_context_development(
            x_organization_id, x_project_id, x_actor_id, x_request_id, x_correlation_id
        )

    # Keycloak mode — principal must be resolved by authentication dependency
    if principal is None:
        raise TenantContextMissing(
            "authenticated principal is required in keycloak mode"
        )

    factory = TenantContextFactory()
    return factory.create(
        principal,
        organization_id=x_organization_id,
        project_id=x_project_id,
        correlation_id=x_correlation_id,
        request_id=x_request_id,
    )


def get_compatible_tenant_context(
    x_organization_id: str | None = Header(
        default=None, alias="X-AI-Governance-Organization-Id"
    ),
    x_project_id: str | None = Header(default=None, alias="X-AI-Governance-Project-Id"),
    x_actor_id: str | None = Header(default=None, alias="X-AI-Governance-Actor-Id"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    principal: AuthenticatedPrincipal = Depends(get_authenticated_principal),
) -> TenantContext:
    """Compatibility resolver for existing routes during tenant migration."""
    auth_mode = os.getenv("AI_GOVERNANCE_AUTH_MODE", "development").strip().lower()

    if auth_mode == "development":
        return get_tenant_context(
            x_organization_id
            or os.getenv("AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID", "org_default"),
            x_project_id
            or os.getenv("AI_GOVERNANCE_BOOTSTRAP_PROJECT_ID", "project_default"),
            x_actor_id,
            x_request_id,
            x_correlation_id,
        )

    if principal is None:
        raise TenantContextMissing(
            "authenticated principal is required in keycloak mode"
        )

    factory = TenantContextFactory()
    return factory.create(
        principal,
        organization_id=x_organization_id,
        project_id=x_project_id,
        correlation_id=x_correlation_id,
        request_id=x_request_id,
    )
