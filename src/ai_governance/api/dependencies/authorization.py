from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request

from ai_governance.api.dependencies.tenancy import (
    get_compatible_tenant_context,
    get_control_plane_service,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.permissions import Permission
from ai_governance.api.dependencies.repositories import get_policy_administration_repository
from ai_governance.services.policies import PolicyAdminNotFoundError


def enforce_permission(permission: Permission | str) -> Callable:
    def dependency(
        context: TenantContext = Depends(get_compatible_tenant_context),
        service=Depends(get_control_plane_service),
    ) -> None:
        service.require(context, permission)

    return dependency


def enforce_read_write(
    read_permission: Permission, write_permission: Permission
) -> Callable:
    def dependency(
        request: Request,
        context: TenantContext = Depends(get_compatible_tenant_context),
        service=Depends(get_control_plane_service),
    ) -> None:
        permission = (
            read_permission
            if request.method in {"GET", "HEAD", "OPTIONS"}
            else write_permission
        )
        service.require(context, permission)

    return dependency


def enforce_replay_permission(
    request: Request,
    context: TenantContext = Depends(get_compatible_tenant_context),
    service=Depends(get_control_plane_service),
) -> None:
    if request.url.path.endswith("/result"):
        permission = Permission.REPLAY_RESULT_READ
    elif request.method in {"GET", "HEAD", "OPTIONS"}:
        permission = Permission.REPLAY_READ
    elif request.url.path.endswith("/archive"):
        permission = Permission.REPLAY_ARCHIVE
    elif request.url.path.endswith("/submit"):
        permission = Permission.REPLAY_EXECUTE
    elif request.url.path.endswith("/cancel"):
        permission = Permission.REPLAY_CANCEL
    elif request.url.path.endswith("/evaluate"):
        permission = Permission.REPLAY_EVALUATE
    else:
        permission = Permission.REPLAY_CREATE
    service.require(context, permission)


def enforce_policy_permission(
    request: Request,
    context: TenantContext = Depends(get_compatible_tenant_context),
    service=Depends(get_control_plane_service),
    policy_repository=Depends(get_policy_administration_repository),
) -> None:
    path = request.url.path
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        permission = Permission.POLICY_READ
    elif path == "/api/v1/policies" and request.method == "POST":
        permission = Permission.POLICY_CREATE
    elif path.endswith("/simulate"):
        permission = Permission.POLICY_SIMULATE
    elif path.endswith("/validate"):
        permission = Permission.POLICY_VALIDATE
    elif path.endswith("/activate"):
        permission = Permission.POLICY_PUBLISH
    elif path.endswith("/archive"):
        permission = Permission.POLICY_DEPRECATE
    else:
        permission = Permission.POLICY_UPDATE
    service.require(context, permission)
    policy_id = request.path_params.get("policy_id")
    if policy_id:
        definition = policy_repository.get_definition(policy_id)
        if definition is None or (
            definition.organization_id != context.organization_id
            or definition.project_id != context.project_id
        ):
            raise PolicyAdminNotFoundError(f"Policy '{policy_id}' does not exist.")
