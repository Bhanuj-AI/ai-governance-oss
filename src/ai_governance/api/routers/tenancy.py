from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ai_governance.api.dependencies.tenancy import (
    get_authorization_service,
    get_control_plane_repository,
    get_control_plane_service,
    get_tenant_context,
)
from ai_governance.api.models.tenancy import (
    ContextResponse,
    MembershipCreateRequest,
    MembershipResponse,
    MembershipUpdateRequest,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
    PermissionResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    RoleAssignmentCreateRequest,
    RoleAssignmentResponse,
    RoleDefinitionResponse,
)
from ai_governance.tenancy.domain import (
    MembershipStatus,
    OrganizationStatus,
    ProjectStatus,
    TenantContext,
)
from ai_governance.tenancy.errors import AuthorizationDenied, TenantScopeMismatch
from ai_governance.tenancy.permissions import (
    PERMISSION_MODEL_VERSION,
    ROLE_PERMISSIONS,
    Permission,
)

router = APIRouter(prefix="/api/v1", tags=["Organizations","Access"])


def _scope(context: TenantContext, organization_id: str) -> None:
    if context.organization_id != organization_id:
        raise TenantScopeMismatch(organization_id)


def _permission_name(permission: Permission | str) -> str:
    """Serialize built-in and plugin-defined permissions for API responses."""
    return permission.value if isinstance(permission, Permission) else permission


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    request: OrganizationCreateRequest,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    return service.create_organization(
        organization_id=request.organization_id,
        name=request.name,
        slug=request.slug,
        actor_id=context.actor_id,
    )


@router.get("/organizations", response_model=list[OrganizationResponse])
def list_organizations(
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    return service.list_organizations(context.actor_id)


@router.get("/organizations/{organization_id}", response_model=OrganizationResponse)
def get_organization(
    organization_id: str,
    context=Depends(get_tenant_context),
    repository=Depends(get_control_plane_repository),
    authorization=Depends(get_authorization_service),
):
    _scope(context, organization_id)
    decision = authorization.authorize(context, Permission.ORGANIZATION_READ)
    if not decision.allowed:
        raise AuthorizationDenied(decision)
    return repository.get_organization(organization_id)


@router.patch("/organizations/{organization_id}", response_model=OrganizationResponse)
def update_organization(
    organization_id: str,
    request: OrganizationUpdateRequest,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    return service.update_organization(context, name=request.name, slug=request.slug)


def _organization_lifecycle(
    organization_id: str, action: str, context: TenantContext, service
):
    _scope(context, organization_id)
    states = {
        "suspend": OrganizationStatus.SUSPENDED,
        "activate": OrganizationStatus.ACTIVE,
        "archive": OrganizationStatus.ARCHIVED,
    }
    if action not in states:
        raise ValueError("unsupported organization lifecycle action")
    return service.update_organization(context, status=states[action])


@router.post(
    "/organizations/{organization_id}/suspend", response_model=OrganizationResponse
)
def suspend_organization(
    organization_id: str,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    return _organization_lifecycle(organization_id, "suspend", context, service)


@router.post(
    "/organizations/{organization_id}/activate", response_model=OrganizationResponse
)
def activate_organization(
    organization_id: str,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    return _organization_lifecycle(organization_id, "activate", context, service)


@router.post(
    "/organizations/{organization_id}/archive", response_model=OrganizationResponse
)
def archive_organization(
    organization_id: str,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    return _organization_lifecycle(organization_id, "archive", context, service)


@router.post(
    "/organizations/{organization_id}/projects",
    response_model=ProjectResponse,
    status_code=201,
)
def create_project(
    organization_id: str,
    request: ProjectCreateRequest,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    return service.create_project(
        context,
        project_id=request.project_id,
        name=request.name,
        slug=request.slug,
        description=request.description,
    )


@router.get(
    "/organizations/{organization_id}/projects", response_model=list[ProjectResponse]
)
def list_projects(
    organization_id: str,
    context=Depends(get_tenant_context),
    repository=Depends(get_control_plane_repository),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    service.require(context, Permission.PROJECT_READ)
    return repository.list_projects(organization_id)


@router.get(
    "/organizations/{organization_id}/projects/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    organization_id: str,
    project_id: str,
    context=Depends(get_tenant_context),
    repository=Depends(get_control_plane_repository),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    service.require(context, Permission.PROJECT_READ)
    return repository.get_project(organization_id, project_id)


@router.patch(
    "/organizations/{organization_id}/projects/{project_id}",
    response_model=ProjectResponse,
)
def update_project(
    organization_id: str,
    project_id: str,
    request: ProjectUpdateRequest,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    return service.update_project(
        context,
        project_id,
        name=request.name,
        slug=request.slug,
        description=request.description,
    )


@router.post(
    "/organizations/{organization_id}/projects/{project_id}/{action}",
    response_model=ProjectResponse,
)
def project_lifecycle(
    organization_id: str,
    project_id: str,
    action: str,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    states = {
        "suspend": ProjectStatus.SUSPENDED,
        "activate": ProjectStatus.ACTIVE,
        "archive": ProjectStatus.ARCHIVED,
    }
    if action not in states:
        raise ValueError("unsupported project lifecycle action")
    return service.update_project(context, project_id, status=states[action])


@router.post(
    "/organizations/{organization_id}/members",
    response_model=MembershipResponse,
    status_code=201,
)
def add_member(
    organization_id: str,
    request: MembershipCreateRequest,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    return service.add_membership(context, request.actor_id, request.display_name)


@router.get(
    "/organizations/{organization_id}/members", response_model=list[MembershipResponse]
)
def list_members(
    organization_id: str,
    context=Depends(get_tenant_context),
    repository=Depends(get_control_plane_repository),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    service.require(context, Permission.MEMBERSHIP_READ)
    return repository.list_memberships(organization_id)


@router.get(
    "/organizations/{organization_id}/members/{actor_id}",
    response_model=MembershipResponse,
)
def get_member(
    organization_id: str,
    actor_id: str,
    context=Depends(get_tenant_context),
    repository=Depends(get_control_plane_repository),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    service.require(context, Permission.MEMBERSHIP_READ)
    return repository.get_membership(organization_id, actor_id)


@router.patch(
    "/organizations/{organization_id}/members/{actor_id}",
    response_model=MembershipResponse,
)
def update_member(
    organization_id: str,
    actor_id: str,
    request: MembershipUpdateRequest,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    return service.update_membership(context, actor_id, request.status)


@router.post(
    "/organizations/{organization_id}/members/{actor_id}/remove",
    response_model=MembershipResponse,
)
def remove_member(
    organization_id: str,
    actor_id: str,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    return service.update_membership(context, actor_id, MembershipStatus.REMOVED)


@router.post(
    "/organizations/{organization_id}/role-assignments",
    response_model=RoleAssignmentResponse,
    status_code=201,
)
def assign_role(
    organization_id: str,
    request: RoleAssignmentCreateRequest,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    return service.assign_role(
        context, request.actor_id, request.role, request.project_id
    )


@router.get(
    "/organizations/{organization_id}/role-assignments",
    response_model=list[RoleAssignmentResponse],
)
def list_roles(
    organization_id: str,
    context=Depends(get_tenant_context),
    repository=Depends(get_control_plane_repository),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    service.require(context, Permission.ROLE_ASSIGNMENT_READ)
    return repository.list_assignments(organization_id)


@router.delete(
    "/organizations/{organization_id}/role-assignments/{assignment_id}",
    response_model=RoleAssignmentResponse,
)
def remove_role(
    organization_id: str,
    assignment_id: str,
    context=Depends(get_tenant_context),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    return service.remove_assignment(context, assignment_id)


@router.get(
    "/organizations/{organization_id}/actors/{actor_id}/permissions",
    response_model=PermissionResponse,
)
def actor_permissions(
    organization_id: str,
    actor_id: str,
    context=Depends(get_tenant_context),
    repository=Depends(get_control_plane_repository),
    authorization=Depends(get_authorization_service),
    service=Depends(get_control_plane_service),
):
    _scope(context, organization_id)
    service.require(context, Permission.ROLE_ASSIGNMENT_READ)
    target = TenantContext(
        organization_id,
        context.project_id,
        actor_id,
        context.request_id,
        context.correlation_id,
    )
    roles = sorted(
        {
            item.role
            for item in repository.list_assignments(
                organization_id, actor_id, context.project_id
            )
        },
        key=lambda x: x.value,
    )
    return PermissionResponse(
        actor_id=actor_id,
        roles=roles,
        permissions=sorted(_permission_name(item) for item in authorization.permissions(target)),
        permission_model_version=PERMISSION_MODEL_VERSION,
    )


@router.get("/context", response_model=ContextResponse)
def current_context(
    context=Depends(get_tenant_context),
    repository=Depends(get_control_plane_repository),
    authorization=Depends(get_authorization_service),
):
    organization = repository.get_organization(context.organization_id)
    project = (
        repository.get_project(context.organization_id, context.project_id)
        if context.project_id
        else None
    )
    roles = sorted(
        {
            item.role
            for item in repository.list_assignments(
                context.organization_id, context.actor_id, context.project_id
            )
        },
        key=lambda x: x.value,
    )
    return ContextResponse(
        actor={
            "actor_id": context.actor_id,
            "actor_type": "USER",
            "display_name": None,
        },
        organization={
            "organization_id": organization.organization_id,
            "name": organization.name,
        },
        project={"project_id": project.project_id, "name": project.name}
        if project
        else None,
        roles=roles,
        permissions=sorted(
            _permission_name(item) for item in authorization.permissions(context)
        ),
        permission_model_version=PERMISSION_MODEL_VERSION,
    )


@router.get("/roles", response_model=list[RoleDefinitionResponse])
def role_definitions(
    context=Depends(get_tenant_context), service=Depends(get_control_plane_service)
):
    service.require(context, Permission.ROLE_ASSIGNMENT_READ)
    return [
        RoleDefinitionResponse(
            role=role,
            permissions=sorted(
                permission.value for permission in ROLE_PERMISSIONS[role]
            ),
            permission_model_version=PERMISSION_MODEL_VERSION,
        )
        for role in sorted(ROLE_PERMISSIONS, key=lambda item: item.value)
    ]
