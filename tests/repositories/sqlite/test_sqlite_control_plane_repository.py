from __future__ import annotations

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.tenancy.authorization import AuthorizationService
from ai_governance.tenancy.domain import MembershipStatus, TenantContext
from ai_governance.tenancy.errors import LastOrganizationAdministrator, ProjectNotFound
from ai_governance.tenancy.permissions import Permission
from ai_governance.tenancy.services import ControlPlaneService, bootstrap_control_plane
from ai_governance.tenancy.sqlite_repository import SQLiteControlPlaneRepository


@pytest.fixture
def repository(tmp_path):
    database = SQLiteDatabase(tmp_path / "tenancy.db")
    return SQLiteControlPlaneRepository(database)


def test_bootstrap_is_idempotent_and_persistent(repository):
    arguments = {
        "organization_id": "org_a",
        "organization_name": "A",
        "organization_slug": "a",
        "project_id": "project_a",
        "project_name": "A",
        "project_slug": "a",
        "administrator_actor_id": "admin",
    }
    bootstrap_control_plane(repository, **arguments)
    bootstrap_control_plane(repository, **arguments)
    assert repository.get_organization("org_a").slug == "a"
    assert repository.get_project("org_a", "project_a").slug == "a"
    assert len(repository.list_assignments("org_a", "admin")) == 1


def test_project_lookup_is_tenant_scoped(repository):
    bootstrap_control_plane(
        repository,
        organization_id="org_a",
        organization_name="A",
        organization_slug="a",
        project_id="project_a",
        project_name="A",
        project_slug="a",
        administrator_actor_id="admin",
    )
    with pytest.raises(ProjectNotFound):
        repository.get_project("org_b", "project_a")


def test_last_administrator_guard_works_with_sqlite(repository):
    bootstrap_control_plane(
        repository,
        organization_id="org_a",
        organization_name="A",
        organization_slug="a",
        project_id="project_a",
        project_name="A",
        project_slug="a",
        administrator_actor_id="admin",
    )
    service = ControlPlaneService(repository, AuthorizationService(repository))
    with pytest.raises(LastOrganizationAdministrator):
        service.update_membership(
            TenantContext("org_a", None, "admin", "request"),
            "admin",
            MembershipStatus.REMOVED,
        )


def test_authorization_denial_is_persisted(repository):
    bootstrap_control_plane(
        repository,
        organization_id="org_a",
        organization_name="A",
        organization_slug="a",
        project_id="project_a",
        project_name="A",
        project_slug="a",
        administrator_actor_id="admin",
    )
    authorization = AuthorizationService(repository)
    authorization.authorize(
        TenantContext("org_a", "project_a", "unknown", "request-denied"),
        Permission.POLICY_READ,
    )
    with repository.database.connect() as connection:
        row = connection.execute(
            "SELECT request_id, authorization_result FROM authorization_audit "
            "WHERE request_id='request-denied'"
        ).fetchone()
    assert tuple(row) == ("request-denied", 0)
