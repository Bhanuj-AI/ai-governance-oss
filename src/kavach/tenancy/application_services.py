from __future__ import annotations

from .authorization import AuthorizationDecision, AuthorizationService
from .domain import AuthorizationResource, BuiltInRole, MembershipStatus, TenantContext
from .permissions import Permission
from .services import ControlPlaneService


class OrganizationApplicationService:
    def __init__(self, service: ControlPlaneService) -> None:
        self._service = service

    def create(self, **kwargs):
        return self._service.create_organization(**kwargs)

    def list_accessible(self, actor_id: str):
        return self._service.list_organizations(actor_id)

    def update(self, context: TenantContext, **kwargs):
        return self._service.update_organization(context, **kwargs)


class ProjectApplicationService:
    def __init__(self, service: ControlPlaneService) -> None:
        self._service = service

    def create(self, context: TenantContext, **kwargs):
        return self._service.create_project(context, **kwargs)

    def update(self, context: TenantContext, project_id: str, **kwargs):
        return self._service.update_project(context, project_id, **kwargs)


class MembershipApplicationService:
    def __init__(self, service: ControlPlaneService) -> None:
        self._service = service

    def add(
        self, context: TenantContext, actor_id: str, display_name: str | None = None
    ):
        return self._service.add_membership(context, actor_id, display_name)

    def update_status(
        self, context: TenantContext, actor_id: str, status: MembershipStatus
    ):
        return self._service.update_membership(context, actor_id, status)


class RoleAssignmentApplicationService:
    def __init__(self, service: ControlPlaneService) -> None:
        self._service = service

    def assign(
        self,
        context: TenantContext,
        actor_id: str,
        role: BuiltInRole,
        project_id: str | None = None,
    ):
        return self._service.assign_role(context, actor_id, role, project_id)

    def remove(self, context: TenantContext, assignment_id: str):
        return self._service.remove_assignment(context, assignment_id)


class AuthorizationApplicationService:
    def __init__(self, authorization: AuthorizationService) -> None:
        self._authorization = authorization

    def authorize(
        self,
        context: TenantContext,
        permission: Permission,
        resource: AuthorizationResource | None = None,
    ) -> AuthorizationDecision:
        return self._authorization.authorize(context, permission, resource)

    def effective_permissions(self, context: TenantContext) -> frozenset[Permission]:
        return self._authorization.permissions(context)
