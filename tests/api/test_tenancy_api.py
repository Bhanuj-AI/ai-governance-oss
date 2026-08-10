from ai_governance.api.routers.tenancy import actor_permissions, current_context
from ai_governance.tenancy import permissions
from ai_governance.tenancy.authorization import AuthorizationService
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.permissions import Permission
from ai_governance.tenancy.repository import InMemoryControlPlaneRepository
from ai_governance.tenancy.services import ControlPlaneService, bootstrap_control_plane


def test_context_and_actor_permissions_serialize_extension_permissions(monkeypatch) -> None:
    repository = InMemoryControlPlaneRepository()
    bootstrap_control_plane(
        repository,
        organization_id="org_a",
        organization_name="Organization A",
        organization_slug="organization-a",
        project_id="project_a",
        project_name="Project A",
        project_slug="project-a",
        administrator_actor_id="admin",
    )
    authorization = AuthorizationService(repository)
    service = ControlPlaneService(repository, authorization)
    context = TenantContext("org_a", "project_a", "admin", "request_a")
    monkeypatch.setattr(
        permissions, "_EXTENSION_PERMISSIONS", {"plugin.capability.read"}
    )

    current = current_context(context, repository, authorization)
    actor = actor_permissions(
        "org_a", "admin", context, repository, authorization, service
    )

    assert "plugin.capability.read" in current.permissions
    assert "plugin.capability.read" in actor.permissions
    assert Permission.ORGANIZATION_READ.value in current.permissions
    assert Permission.ORGANIZATION_READ.value in actor.permissions
