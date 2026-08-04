from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .domain import (
    AuthorizationResource,
    BuiltInRole,
    MembershipStatus,
    OrganizationStatus,
    ProjectStatus,
    TenantContext,
    utcnow,
)
from .errors import MembershipNotFound, ProjectNotFound
from .permissions import PERMISSION_MODEL_VERSION, Permission, role_permissions
from .repository import InMemoryControlPlaneRepository


class AuthorizationReasonCode(str, Enum):
    ALLOWED_BY_ROLE = "ALLOWED_BY_ROLE"
    ACTOR_NOT_MEMBER = "ACTOR_NOT_MEMBER"
    MEMBERSHIP_INACTIVE = "MEMBERSHIP_INACTIVE"
    NO_ROLE_ASSIGNMENT = "NO_ROLE_ASSIGNMENT"
    PERMISSION_NOT_GRANTED = "PERMISSION_NOT_GRANTED"
    ORGANIZATION_INACTIVE = "ORGANIZATION_INACTIVE"
    PROJECT_INACTIVE = "PROJECT_INACTIVE"
    TENANT_SCOPE_MISMATCH = "TENANT_SCOPE_MISMATCH"


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    permission: Permission | str
    matched_roles: tuple[BuiltInRole, ...]
    reason_code: AuthorizationReasonCode
    permission_model_version: str = PERMISSION_MODEL_VERSION


@dataclass(frozen=True)
class AuthorizationAuditRecord:
    organization_id: str
    project_id: str | None
    actor_id: str
    operation: str
    permission: Permission | str
    authorization_result: bool
    reason_code: AuthorizationReasonCode
    matched_roles: tuple[BuiltInRole, ...]
    permission_model_version: str
    resource_type: str | None
    resource_id: str | None
    request_id: str
    correlation_id: str | None
    occurred_at: datetime


class AuthorizationService:
    def __init__(self, repository: InMemoryControlPlaneRepository) -> None:
        self.repository = repository
        self.audit_records: list[AuthorizationAuditRecord] = []
        self.decision_metrics: dict[tuple[str, bool, str], int] = {}

    def authorize(
        self,
        context: TenantContext,
        permission: Permission | str,
        resource: AuthorizationResource | None = None,
    ) -> AuthorizationDecision:
        def denied(reason: AuthorizationReasonCode) -> AuthorizationDecision:
            decision = AuthorizationDecision(False, permission, (), reason)
            self._record(context, decision, resource)
            return decision

        try:
            organization = self.repository.get_organization(context.organization_id)
        except Exception:
            return denied(AuthorizationReasonCode.TENANT_SCOPE_MISMATCH)
        if (
            organization.status is OrganizationStatus.ARCHIVED
            and permission is not Permission.ORGANIZATION_READ
        ):
            return denied(AuthorizationReasonCode.ORGANIZATION_INACTIVE)
        if organization.status is OrganizationStatus.SUSPENDED and permission not in {
            Permission.ORGANIZATION_READ,
            Permission.ORGANIZATION_UPDATE,
            Permission.PROJECT_READ,
            Permission.MEMBERSHIP_READ,
            Permission.ROLE_ASSIGNMENT_READ,
            Permission.AUDIT_READ,
        }:
            return denied(AuthorizationReasonCode.ORGANIZATION_INACTIVE)
        try:
            membership = self.repository.get_membership(
                context.organization_id, context.actor_id
            )
        except MembershipNotFound:
            return denied(AuthorizationReasonCode.ACTOR_NOT_MEMBER)
        if membership.status is not MembershipStatus.ACTIVE:
            return denied(AuthorizationReasonCode.MEMBERSHIP_INACTIVE)
        if resource and (
            (
                resource.organization_id
                and resource.organization_id != context.organization_id
            )
            or (resource.project_id and resource.project_id != context.project_id)
        ):
            return denied(AuthorizationReasonCode.TENANT_SCOPE_MISMATCH)
        if context.project_id:
            try:
                project = self.repository.get_project(
                    context.organization_id, context.project_id
                )
            except ProjectNotFound:
                return denied(AuthorizationReasonCode.TENANT_SCOPE_MISMATCH)
            if project.status is not ProjectStatus.ACTIVE:
                return denied(AuthorizationReasonCode.PROJECT_INACTIVE)
        assignments = self.repository.list_assignments(
            context.organization_id, context.actor_id, context.project_id
        )
        if not assignments:
            return denied(AuthorizationReasonCode.NO_ROLE_ASSIGNMENT)
        roles = tuple(
            sorted(
                {
                    item.role
                    for item in assignments
                    if item.project_id is None or item.project_id == context.project_id
                },
                key=lambda role: role.value,
            )
        )
        matched = tuple(role for role in roles if permission in role_permissions(role))
        if matched:
            decision = AuthorizationDecision(
                True, permission, matched, AuthorizationReasonCode.ALLOWED_BY_ROLE
            )
            self._record(context, decision, resource)
            return decision
        decision = AuthorizationDecision(
            False, permission, roles, AuthorizationReasonCode.PERMISSION_NOT_GRANTED
        )
        self._record(context, decision, resource)
        return decision

    def permissions(self, context: TenantContext) -> frozenset[Permission | str]:
        assignments = self.repository.list_assignments(
            context.organization_id, context.actor_id, context.project_id
        )
        return frozenset(
            permission
            for item in assignments
            if item.project_id is None or item.project_id == context.project_id
            for permission in role_permissions(item.role)
        )

    def _record(
        self,
        context: TenantContext,
        decision: AuthorizationDecision,
        resource: AuthorizationResource | None,
    ) -> None:
        key = (
            decision.permission.value if isinstance(decision.permission, Permission) else decision.permission,
            decision.allowed,
            decision.reason_code.value,
        )
        self.decision_metrics[key] = self.decision_metrics.get(key, 0) + 1
        security_write = decision.permission in {
            Permission.ORGANIZATION_UPDATE,
            Permission.PROJECT_CREATE,
            Permission.PROJECT_UPDATE,
            Permission.PROJECT_ARCHIVE,
            Permission.MEMBERSHIP_MANAGE,
            Permission.ROLE_ASSIGNMENT_MANAGE,
        }
        if decision.allowed and not security_write:
            return
        record = AuthorizationAuditRecord(
            organization_id=context.organization_id,
            project_id=context.project_id,
            actor_id=context.actor_id,
            operation=decision.permission.value if isinstance(decision.permission, Permission) else decision.permission,
            permission=decision.permission,
            authorization_result=decision.allowed,
            reason_code=decision.reason_code,
            matched_roles=decision.matched_roles,
            permission_model_version=decision.permission_model_version,
            resource_type=resource.resource_type if resource else None,
            resource_id=resource.resource_id if resource else None,
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            occurred_at=utcnow(),
        )
        self.audit_records.append(record)
        persist = getattr(self.repository, "save_authorization_audit", None)
        if persist is not None:
            persist(record)
