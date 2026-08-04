from __future__ import annotations

import os
from dataclasses import replace
from uuid import uuid4

from .authorization import AuthorizationService
from .domain import (
    BuiltInRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
    Project,
    ProjectStatus,
    RoleAssignment,
    TenantContext,
    utcnow,
    validate_slug,
)
from .errors import (
    AuthorizationDenied,
    LastOrganizationAdministrator,
    OrganizationInactive,
)
from .permissions import Permission
from .repository import InMemoryControlPlaneRepository


def provision_mcp_service_account(
    repository: InMemoryControlPlaneRepository,
    *,
    organization_id: str,
    actor_id: str | None = None,
) -> None:
    """Idempotently provision the configured MCP service-account subject."""
    actor_id = actor_id or os.getenv("KAVACH_MCP_ACTOR_ID")
    _provision_service_account(
        repository,
        organization_id=organization_id,
        actor_id=actor_id,
        display_name="Kavach MCP service account",
        role_prefix="mcp",
        role=BuiltInRole.PLATFORM_OPERATOR,
    )


def provision_walkthrough_service_account(
    repository: InMemoryControlPlaneRepository,
    *,
    organization_id: str,
    actor_id: str | None = None,
) -> None:
    """Idempotently provision the walkthrough workload's service subject."""
    actor_id = actor_id or os.getenv("KAVACH_WALKTHROUGH_ACTOR_ID")
    _provision_service_account(
        repository,
        organization_id=organization_id,
        actor_id=actor_id,
        display_name="Kavach walkthrough service account",
        role_prefix="walkthrough",
        role=BuiltInRole.GOVERNANCE_ADMIN,
    )
    if actor_id:
        legacy_assignment_id = f"role_walkthrough_{actor_id.replace('-', '')}"
        try:
            legacy_assignment = repository.get_assignment(organization_id, legacy_assignment_id)
        except Exception:
            return
        if legacy_assignment.role is BuiltInRole.PLATFORM_OPERATOR:
            repository.delete_assignment(organization_id, legacy_assignment_id)


def _provision_service_account(
    repository: InMemoryControlPlaneRepository,
    *,
    organization_id: str,
    actor_id: str | None,
    display_name: str,
    role_prefix: str,
    role: BuiltInRole,
) -> None:
    """Provision one service subject through the normal membership/RBAC model."""
    if not actor_id:
        return
    now = utcnow()
    try:
        membership = repository.get_membership(organization_id, actor_id)
        if membership.status is not MembershipStatus.ACTIVE:
            repository.update_membership(replace(membership, status=MembershipStatus.ACTIVE, updated_at=now))
    except Exception:
        repository.create_membership(
            OrganizationMembership(
                organization_id, actor_id, MembershipStatus.ACTIVE, now, now,
                display_name,
            )
        )
    if not any(
        item.project_id is None and item.role is role
        for item in repository.list_assignments(organization_id, actor_id)
    ):
        try:
            repository.create_assignment(
                RoleAssignment(
                    f"role_{role_prefix}_{role.value.lower()}_{actor_id.replace('-', '')}",
                    organization_id,
                    None,
                    actor_id, role, now, actor_id,
                )
            )
        except Exception:
            pass


class ControlPlaneService:
    def __init__(
        self,
        repository: InMemoryControlPlaneRepository,
        authorization: AuthorizationService,
    ) -> None:
        self.repository = repository
        self.authorization = authorization

    def require(self, context: TenantContext, permission: Permission) -> None:
        decision = self.authorization.authorize(context, permission)
        if not decision.allowed:
            raise AuthorizationDenied(decision)

    def create_organization(
        self,
        *,
        organization_id: str,
        name: str,
        slug: str,
        actor_id: str,
        actor_name: str | None = None,
    ) -> Organization:
        now = utcnow()
        organization = self.repository.create_organization(
            Organization(
                organization_id,
                name.strip(),
                validate_slug(slug),
                OrganizationStatus.ACTIVE,
                now,
                now,
            )
        )
        self.repository.create_membership(
            OrganizationMembership(
                organization_id, actor_id, MembershipStatus.ACTIVE, now, now, actor_name
            )
        )
        self.repository.create_assignment(
            RoleAssignment(
                f"role_{uuid4().hex}",
                organization_id,
                None,
                actor_id,
                BuiltInRole.ORGANIZATION_ADMIN,
                now,
                actor_id,
            )
        )
        return organization

    def list_organizations(self, actor_id: str) -> list[Organization]:
        return [
            organization
            for organization in self.repository.list_organizations()
            if any(
                member.actor_id == actor_id and member.status is MembershipStatus.ACTIVE
                for member in self.repository.list_memberships(
                    organization.organization_id
                )
            )
        ]

    def update_organization(
        self,
        context: TenantContext,
        *,
        name: str | None = None,
        slug: str | None = None,
        status: OrganizationStatus | None = None,
    ) -> Organization:
        self.require(context, Permission.ORGANIZATION_UPDATE)
        current = self.repository.get_organization(context.organization_id)
        if current.status is OrganizationStatus.ARCHIVED:
            raise OrganizationInactive(current.organization_id)
        return self.repository.update_organization(
            replace(
                current,
                name=name.strip() if name else current.name,
                slug=validate_slug(slug) if slug else current.slug,
                status=status or current.status,
                updated_at=utcnow(),
            )
        )

    def create_project(
        self,
        context: TenantContext,
        *,
        project_id: str,
        name: str,
        slug: str,
        description: str | None = None,
    ) -> Project:
        self.require(context, Permission.PROJECT_CREATE)
        now = utcnow()
        return self.repository.create_project(
            Project(
                project_id,
                context.organization_id,
                name.strip(),
                validate_slug(slug),
                description,
                ProjectStatus.ACTIVE,
                now,
                now,
            )
        )

    def update_project(
        self,
        context: TenantContext,
        project_id: str,
        *,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
    ) -> Project:
        self.require(
            context,
            Permission.PROJECT_ARCHIVE
            if status is ProjectStatus.ARCHIVED
            else Permission.PROJECT_UPDATE,
        )
        current = self.repository.get_project(context.organization_id, project_id)
        if current.status is ProjectStatus.ARCHIVED:
            raise OrganizationInactive(project_id)
        return self.repository.update_project(
            replace(
                current,
                name=name.strip() if name else current.name,
                slug=validate_slug(slug) if slug else current.slug,
                description=current.description if description is None else description,
                status=status or current.status,
                updated_at=utcnow(),
            )
        )

    def add_membership(
        self, context: TenantContext, actor_id: str, display_name: str | None = None
    ) -> OrganizationMembership:
        self.require(context, Permission.MEMBERSHIP_MANAGE)
        now = utcnow()
        return self.repository.create_membership(
            OrganizationMembership(
                context.organization_id,
                actor_id,
                MembershipStatus.ACTIVE,
                now,
                now,
                display_name,
            )
        )

    def update_membership(
        self, context: TenantContext, actor_id: str, status: MembershipStatus
    ) -> OrganizationMembership:
        self.require(context, Permission.MEMBERSHIP_MANAGE)
        with self.repository.lock:
            current = self.repository.get_membership(context.organization_id, actor_id)
            if status is not MembershipStatus.ACTIVE:
                self._protect_last_admin(context.organization_id, actor_id)
            return self.repository.update_membership(
                replace(current, status=status, updated_at=utcnow())
            )

    def assign_role(
        self,
        context: TenantContext,
        actor_id: str,
        role: BuiltInRole,
        project_id: str | None = None,
    ) -> RoleAssignment:
        self.require(context, Permission.ROLE_ASSIGNMENT_MANAGE)
        return self.repository.create_assignment(
            RoleAssignment(
                f"role_{uuid4().hex}",
                context.organization_id,
                project_id,
                actor_id,
                role,
                utcnow(),
                context.actor_id,
            )
        )

    def remove_assignment(
        self, context: TenantContext, assignment_id: str
    ) -> RoleAssignment:
        self.require(context, Permission.ROLE_ASSIGNMENT_MANAGE)
        with self.repository.lock:
            assignment = self.repository.get_assignment(
                context.organization_id, assignment_id
            )
            if (
                assignment.role is BuiltInRole.ORGANIZATION_ADMIN
                and assignment.project_id is None
            ):
                self._protect_last_admin(
                    context.organization_id, assignment.actor_id, assignment_id
                )
            return self.repository.delete_assignment(
                context.organization_id, assignment_id
            )

    def _protect_last_admin(
        self,
        organization_id: str,
        actor_id: str,
        excluded_assignment_id: str | None = None,
    ) -> None:
        active_admins = {
            assignment.actor_id
            for assignment in self.repository.list_assignments(organization_id)
            if assignment.role is BuiltInRole.ORGANIZATION_ADMIN
            and assignment.project_id is None
            and assignment.assignment_id != excluded_assignment_id
            and self.repository.get_membership(
                organization_id, assignment.actor_id
            ).status
            is MembershipStatus.ACTIVE
            and assignment.actor_id != actor_id
        }
        if not active_admins:
            raise LastOrganizationAdministrator(actor_id)


def _resolve_bootstrap_administrator(
    auth_mode: str,
    *,
    organization_id: str,
    organization_name: str,
    organization_slug: str,
    project_id: str,
    project_name: str,
    project_slug: str,
) -> tuple[str, str | None]:
    """Resolve the initial administrator identity based on authentication mode.

    Development mode
    ----------------
    Uses ``KAVACH_DEVELOPMENT_ACTOR_ID`` (fallback: ``local-admin``) and
    ``KAVACH_DEVELOPMENT_ACTOR_NAME`` (fallback: ``Local Administrator``).

    Keycloak mode
    -------------
    Requires ``KAVACH_BOOTSTRAP_ADMIN_SUB`` (the immutable Keycloak user
    ``sub``). Fails fast if absent. Optionally uses
    ``KAVACH_BOOTSTRAP_ADMIN_NAME`` for display purposes.

    Returns
    -------
    tuple[str, str | None]
        (administrator_actor_id, administrator_name)
    """
    import os

    if auth_mode == "development":
        administrator_actor_id = os.getenv(
            "KAVACH_DEVELOPMENT_ACTOR_ID", "local-admin"
        )
        administrator_name = os.getenv(
            "KAVACH_DEVELOPMENT_ACTOR_NAME", "Local Administrator"
        )
    elif auth_mode == "keycloak":
        administrator_actor_id = os.getenv("KAVACH_BOOTSTRAP_ADMIN_SUB")
        if not administrator_actor_id:
            raise ValueError(
                "KAVACH_BOOTSTRAP_ADMIN_SUB is required when "
                "KAVACH_AUTH_MODE=keycloak. This value must match the "
                "Keycloak JWT sub claim for the intended initial administrator."
            )
        administrator_name = os.getenv("KAVACH_BOOTSTRAP_ADMIN_NAME")
    else:
        raise ValueError(f"Unsupported authentication mode: {auth_mode}")

    return administrator_actor_id, administrator_name


def bootstrap_control_plane(
    repository: InMemoryControlPlaneRepository,
    *,
    organization_id: str,
    organization_name: str,
    organization_slug: str,
    project_id: str,
    project_name: str,
    project_slug: str,
    auth_mode: str = "development",
    administrator_actor_id: str | None = None,
    administrator_name: str | None = None,
) -> None:
    """Idempotently seed the deterministic compatibility tenant.

    The initial administrator identity is resolved from environment variables
    based on ``auth_mode``. See ``_resolve_bootstrap_administrator`` for
    details.

    Parameters
    ----------
    repository : InMemoryControlPlaneRepository
        The control plane repository to seed.
    organization_id, organization_name, organization_slug : str
        Bootstrap organization identifiers.
    project_id, project_name, project_slug : str
        Bootstrap project identifiers.
    auth_mode : str
        Authentication mode: ``development`` or ``keycloak``. Defaults to
        ``development`` for backward compatibility.
    """
    try:
        repository.get_organization(organization_id)
        return
    except Exception:
        pass

    if administrator_actor_id is None:
        administrator_actor_id, administrator_name = _resolve_bootstrap_administrator(
            auth_mode,
            organization_id=organization_id,
            organization_name=organization_name,
            organization_slug=organization_slug,
            project_id=project_id,
            project_name=project_name,
            project_slug=project_slug,
        )
    administrator_actor_id = administrator_actor_id or "local-admin"
    administrator_name = administrator_name or "Local Administrator"

    auth = AuthorizationService(repository)
    service = ControlPlaneService(repository, auth)
    service.create_organization(
        organization_id=organization_id,
        name=organization_name,
        slug=organization_slug,
        actor_id=administrator_actor_id,
        actor_name=administrator_name,
    )
    context = TenantContext(organization_id, None, administrator_actor_id, "bootstrap")
    service.create_project(
        context, project_id=project_id, name=project_name, slug=project_slug
    )
