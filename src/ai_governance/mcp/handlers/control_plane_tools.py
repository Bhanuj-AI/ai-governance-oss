from __future__ import annotations

from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.clients import RestClient
from ai_governance.mcp.dto.requests import (
    AuthorizationPermissionsRequest,
    MembershipAddToolRequest,
    MembershipListRequest,
    MembershipUpdateToolRequest,
    OrganizationCreateToolRequest,
    OrganizationGetRequest,
    OrganizationListRequest,
    OrganizationUpdateToolRequest,
    ProjectCreateToolRequest,
    ProjectGetRequest,
    ProjectListRequest,
    ProjectUpdateToolRequest,
    RoleAssignmentAssignToolRequest,
    RoleAssignmentListRequest,
    RoleAssignmentRemoveToolRequest,
    TenantRequest,
    WriteEnvelope,
)
from ai_governance.mcp.handlers._rest_tool import rest_get, rest_post
from ai_governance.mcp.observability import MCPMetrics
from ai_governance.mcp.registry import ToolRegistry
from ai_governance.mcp.runtime_context import get_runtime_context
from ai_governance.tenancy.domain import ActorType, AuthenticatedPrincipal


def register_control_plane_tools(
    registry: ToolRegistry,
    client: RestClient,
    metrics: MCPMetrics,
    audit_log: MCPExecutionAuditLog,
    principal: AuthenticatedPrincipal,
) -> None:
    def scoped(request: TenantRequest) -> RestClient:
        return client.with_tenant_context(
            request.context.organization_id, request.context.project_id
        )

    def controlled(request, tool_name: str, resource_type: str, rest_call):
        runtime = get_runtime_context()
        authenticated_principal = (
            runtime.principal if runtime and runtime.principal is not None else principal
        )
        actor_type = {
            ActorType.USER: "HUMAN",
            ActorType.SERVICE: "SERVICE",
            ActorType.SYSTEM: "SERVICE",
        }[authenticated_principal.principal_type]
        envelope = WriteEnvelope(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            requested_by=authenticated_principal.subject,
            actor_type=actor_type,
            reason=request.reason,
            dry_run=request.dry_run,
            context=request.context,
        )
        payload = request.model_dump(mode="json")
        record = audit_log.start(
            tool_name=tool_name,
            operation_type=tool_name.upper().replace(".", "_"),
            resource_type=resource_type,
            resource_id=getattr(request, "project_id", None)
            or getattr(request, "actor_id", None)
            or getattr(request, "assignment_id", None),
            envelope=envelope,
            payload=payload,
        )
        if request.dry_run:
            audit_log.complete(record, status="DRY_RUN")
            return {
                "dry_run": True,
                "status": "VALIDATED",
                "request_id": request.request_id,
            }
        try:
            result = rest_call()
            audit_log.complete(record, status="SUCCEEDED")
            return result
        except Exception as exc:
            audit_log.complete(
                record,
                status="FAILED",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

    registry.register(
        name="organization.list",
        description="List accessible organizations.",
        request_model=OrganizationListRequest,
        handler=lambda request: rest_get(
            scoped(request), metrics, "/api/v1/organizations"
        ),
    )
    registry.register(
        name="organization.get",
        description="Get the selected organization.",
        request_model=OrganizationGetRequest,
        handler=lambda request: rest_get(
            scoped(request), metrics, f"/api/v1/organizations/{request.organization_id}"
        ),
    )
    registry.register(
        name="project.list",
        description="List projects in the selected organization.",
        request_model=ProjectListRequest,
        handler=lambda request: rest_get(
            scoped(request),
            metrics,
            f"/api/v1/organizations/{request.context.organization_id}/projects",
        ),
    )
    registry.register(
        name="project.get",
        description="Get a project in the selected organization.",
        request_model=ProjectGetRequest,
        handler=lambda request: rest_get(
            scoped(request),
            metrics,
            f"/api/v1/organizations/{request.context.organization_id}/projects/{request.project_id}",
        ),
    )
    registry.register(
        name="membership.list",
        description="List organization memberships.",
        request_model=MembershipListRequest,
        handler=lambda request: rest_get(
            scoped(request),
            metrics,
            f"/api/v1/organizations/{request.context.organization_id}/members",
        ),
    )
    registry.register(
        name="role_assignment.list",
        description="List role assignments.",
        request_model=RoleAssignmentListRequest,
        handler=lambda request: rest_get(
            scoped(request),
            metrics,
            f"/api/v1/organizations/{request.context.organization_id}/role-assignments",
        ),
    )
    registry.register(
        name="authorization.permissions",
        description="Resolve effective actor permissions.",
        request_model=AuthorizationPermissionsRequest,
        handler=lambda request: rest_get(
            scoped(request),
            metrics,
            f"/api/v1/organizations/{request.context.organization_id}/actors/{request.actor_id}/permissions",
        ),
    )
    registry.register(
        name="context.current",
        description="Return current tenant and authorization context.",
        request_model=OrganizationListRequest,
        handler=lambda request: rest_get(scoped(request), metrics, "/api/v1/context"),
    )
    registry.register(
        name="organization.create",
        description="Create an organization.",
        request_model=OrganizationCreateToolRequest,
        handler=lambda request: controlled(
            request,
            "organization.create",
            "organization",
            lambda: rest_post(
                scoped(request),
                metrics,
                "/api/v1/organizations",
                body={
                    "organization_id": request.organization_id,
                    "name": request.name,
                    "slug": request.slug,
                },
            ),
        ),
    )
    registry.register(
        name="organization.update",
        description="Update the selected organization.",
        request_model=OrganizationUpdateToolRequest,
        handler=lambda request: controlled(
            request,
            "organization.update",
            "organization",
            lambda: scoped(request).request(
                "PATCH",
                f"/api/v1/organizations/{request.context.organization_id}",
                body={"name": request.name, "slug": request.slug},
            ),
        ),
    )
    registry.register(
        name="project.create",
        description="Create a project.",
        request_model=ProjectCreateToolRequest,
        handler=lambda request: controlled(
            request,
            "project.create",
            "project",
            lambda: rest_post(
                scoped(request),
                metrics,
                f"/api/v1/organizations/{request.context.organization_id}/projects",
                body={
                    "project_id": request.project_id,
                    "name": request.name,
                    "slug": request.slug,
                    "description": request.description,
                },
            ),
        ),
    )
    registry.register(
        name="project.update",
        description="Update a project in the selected organization.",
        request_model=ProjectUpdateToolRequest,
        handler=lambda request: controlled(
            request,
            "project.update",
            "project",
            lambda: scoped(request).request(
                "PATCH",
                f"/api/v1/organizations/{request.context.organization_id}/projects/{request.project_id}",
                body={
                    "name": request.name,
                    "slug": request.slug,
                    "description": request.description,
                },
            ),
        ),
    )
    registry.register(
        name="membership.add",
        description="Add an organization membership.",
        request_model=MembershipAddToolRequest,
        handler=lambda request: controlled(
            request,
            "membership.add",
            "membership",
            lambda: rest_post(
                scoped(request),
                metrics,
                f"/api/v1/organizations/{request.context.organization_id}/members",
                body={
                    "actor_id": request.actor_id,
                    "display_name": request.display_name,
                },
            ),
        ),
    )
    registry.register(
        name="membership.update",
        description="Update an organization membership status.",
        request_model=MembershipUpdateToolRequest,
        handler=lambda request: controlled(
            request,
            "membership.update",
            "membership",
            lambda: scoped(request).request(
                "PATCH",
                f"/api/v1/organizations/{request.context.organization_id}/members/{request.actor_id}",
                body={"status": request.status},
            ),
        ),
    )
    registry.register(
        name="role_assignment.assign",
        description="Assign a built-in role.",
        request_model=RoleAssignmentAssignToolRequest,
        handler=lambda request: controlled(
            request,
            "role_assignment.assign",
            "role_assignment",
            lambda: rest_post(
                scoped(request),
                metrics,
                f"/api/v1/organizations/{request.context.organization_id}/role-assignments",
                body={
                    "actor_id": request.actor_id,
                    "role": request.role,
                    "project_id": request.project_id,
                },
            ),
        ),
    )
    registry.register(
        name="role_assignment.remove",
        description="Remove a role assignment.",
        request_model=RoleAssignmentRemoveToolRequest,
        handler=lambda request: controlled(
            request,
            "role_assignment.remove",
            "role_assignment",
            lambda: scoped(request).request(
                "DELETE",
                f"/api/v1/organizations/{request.context.organization_id}/role-assignments/{request.assignment_id}",
            ),
        ),
    )
