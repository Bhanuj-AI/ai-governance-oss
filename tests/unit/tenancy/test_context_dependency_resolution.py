from kavach.api.dependencies.tenancy import (
    get_compatible_tenant_context,
    get_tenant_context,
)
from kavach.tenancy.domain import ActorType, AuthenticatedPrincipal


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        subject="user-1",
        principal_type=ActorType.USER,
        organization_id="jwt-org",
        client_id="client",
        issuer="https://issuer.example",
    )


def test_keycloak_tenant_context_accepts_header_scope(monkeypatch) -> None:
    monkeypatch.setenv("KAVACH_AUTH_MODE", "keycloak")

    context = get_tenant_context(
        x_organization_id="header-org",
        x_project_id="project-1",
        x_request_id="request-1",
        x_correlation_id="correlation-1",
        principal=_principal(),
    )

    assert context.organization_id == "header-org"
    assert context.project_id == "project-1"
    assert context.actor_id == "user-1"
    assert context.request_id == "request-1"
    assert context.correlation_id == "correlation-1"


def test_compatible_keycloak_context_uses_principal_scope_when_headers_absent(
    monkeypatch,
) -> None:
    monkeypatch.setenv("KAVACH_AUTH_MODE", "keycloak")

    context = get_compatible_tenant_context(
        x_organization_id=None,
        x_project_id=None,
        x_actor_id=None,
        x_request_id=None,
        x_correlation_id=None,
        principal=_principal(),
    )

    assert context.organization_id == "jwt-org"
    assert context.project_id is None
    assert context.actor_id == "user-1"
