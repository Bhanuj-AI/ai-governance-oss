from __future__ import annotations

import pytest

from kavach.tenancy.authorization import AuthorizationReasonCode, AuthorizationService
from kavach.tenancy.domain import BuiltInRole, MembershipStatus, TenantContext
from kavach.tenancy.errors import LastOrganizationAdministrator
from kavach.tenancy.permissions import ROLE_PERMISSIONS, Permission
from kavach.tenancy.repository import InMemoryControlPlaneRepository
from kavach.tenancy.services import ControlPlaneService, bootstrap_control_plane


@pytest.fixture
def control_plane(monkeypatch):
    # Ensure development mode uses "admin" as the actor_id for test compatibility
    monkeypatch.setenv("KAVACH_AUTH_MODE", "development")
    monkeypatch.setenv("KAVACH_DEVELOPMENT_ACTOR_ID", "admin")
    monkeypatch.delenv("KAVACH_BOOTSTRAP_ADMIN_SUB", raising=False)

    repository = InMemoryControlPlaneRepository()
    bootstrap_control_plane(
        repository,
        organization_id="org_a",
        organization_name="A",
        organization_slug="a",
        project_id="project_a",
        project_name="A",
        project_slug="a",
        auth_mode="development",
    )
    authorization = AuthorizationService(repository)
    return repository, authorization, ControlPlaneService(repository, authorization)


def test_permission_model_maps_every_role_and_permission():
    assert set(ROLE_PERMISSIONS) == set(BuiltInRole)
    assert ROLE_PERMISSIONS[BuiltInRole.ORGANIZATION_ADMIN] == frozenset(Permission)


@pytest.mark.parametrize("role", list(BuiltInRole))
@pytest.mark.parametrize("permission", list(Permission))
def test_authorization_matrix_is_exact(control_plane, role, permission):
    repository, authorization, service = control_plane
    service.add_membership(TenantContext("org_a", None, "admin", "setup"), role.value)
    service.assign_role(
        TenantContext("org_a", None, "admin", "setup"), role.value, role, "project_a"
    )
    decision = authorization.authorize(
        TenantContext("org_a", "project_a", role.value, "request"), permission
    )
    assert decision.allowed is (permission in ROLE_PERMISSIONS[role])


def test_cross_tenant_project_is_rejected(control_plane):
    repository, authorization, _ = control_plane
    decision = authorization.authorize(
        TenantContext("org_a", "missing", "admin", "request"), Permission.PROJECT_READ
    )
    assert decision.reason_code is AuthorizationReasonCode.TENANT_SCOPE_MISMATCH


def test_last_active_administrator_is_protected(control_plane):
    _, _, service = control_plane
    with pytest.raises(LastOrganizationAdministrator):
        service.update_membership(
            TenantContext("org_a", None, "admin", "request"),
            "admin",
            MembershipStatus.SUSPENDED,
        )


def test_denials_and_security_writes_are_audited(control_plane):
    _, authorization, service = control_plane
    denied = authorization.authorize(
        TenantContext("org_a", "project_a", "unknown", "denied-request"),
        Permission.POLICY_READ,
    )
    assert not denied.allowed
    service.create_project(
        TenantContext("org_a", None, "admin", "allowed-request"),
        project_id="project_b",
        name="B",
        slug="b",
    )
    assert [record.request_id for record in authorization.audit_records] == [
        "denied-request",
        "allowed-request",
    ]
    assert all(
        record.permission_model_version == "1" for record in authorization.audit_records
    )
