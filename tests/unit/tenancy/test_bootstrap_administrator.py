"""
Unit tests for bootstrap administrator identity resolution.

Tests cover:
- Development mode preserves local-admin
- Development mode honours KAVACH_DEVELOPMENT_ACTOR_ID
- Keycloak mode uses KAVACH_BOOTSTRAP_ADMIN_SUB
- Keycloak mode fails when the bootstrap subject is missing
- Bootstrap remains idempotent
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from kavach.tenancy.domain import (
    BuiltInRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
    Project,
    ProjectStatus,
    RoleAssignment,
)
from kavach.tenancy.services import (
    _resolve_bootstrap_administrator,
    bootstrap_control_plane,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repository() -> MagicMock:
    """Create a mock repository that raises on first get_organization call."""
    repo = MagicMock()
    repo.get_organization.side_effect = Exception("not found")
    return repo


def _make_bootstrap_repository(
    actor_id: str = "local-admin",
) -> MagicMock:
    """Create a mock repository configured for successful bootstrap.

    The repository simulates the state after create_organization has been
    called (membership and role assignment exist) so that create_project's
    authorization check passes.
    """
    repo = _make_repository()

    # Mock create methods to track calls
    repo.create_organization = MagicMock(return_value=MagicMock())
    repo.create_membership = MagicMock(return_value=MagicMock())
    repo.create_assignment = MagicMock(return_value=MagicMock())
    repo.create_project = MagicMock(return_value=MagicMock())

    # Mock authorization-check methods to return the bootstrap actor
    # get_organization must return an active organization
    repo.get_organization.return_value = Organization(
        organization_id="org_test",
        name="Test Organization",
        slug="test-org",
        status=OrganizationStatus.ACTIVE,
        created_at=MagicMock(),
        updated_at=MagicMock(),
    )

    # get_membership must return an active membership for the actor
    repo.get_membership.return_value = OrganizationMembership(
        organization_id="org_test",
        actor_id=actor_id,
        status=MembershipStatus.ACTIVE,
        created_at=MagicMock(),
        updated_at=MagicMock(),
    )

    # list_assignments must return role assignments for the actor
    repo.list_assignments.return_value = [
        RoleAssignment(
            assignment_id="role_test",
            organization_id="org_test",
            project_id=None,
            actor_id=actor_id,
            role=BuiltInRole.ORGANIZATION_ADMIN,
            created_at=MagicMock(),
            created_by=actor_id,
        )
    ]

    # get_project must return an active project (for create_project's check)
    repo.get_project.return_value = Project(
        project_id="proj_test",
        organization_id="org_test",
        name="Test Project",
        slug="test-proj",
        description=None,
        status=ProjectStatus.ACTIVE,
        created_at=MagicMock(),
        updated_at=MagicMock(),
    )

    return repo


# ---------------------------------------------------------------------------
# _resolve_bootstrap_administrator — development mode
# ---------------------------------------------------------------------------

class TestResolveBootstrapAdminDeveloperMode:
    def test_uses_local_admin_fallback(self, monkeypatch):
        """Development mode should use local-admin when env vars are absent."""
        monkeypatch.delenv("KAVACH_DEVELOPMENT_ACTOR_ID", raising=False)
        monkeypatch.delenv("KAVACH_DEVELOPMENT_ACTOR_NAME", raising=False)

        actor_id, actor_name = _resolve_bootstrap_administrator(
            "development",
            organization_id="test",
            organization_name="Test",
            organization_slug="test",
            project_id="test",
            project_name="Test",
            project_slug="test",
        )

        assert actor_id == "local-admin"
        assert actor_name == "Local Administrator"

    def test_honours_development_actor_id(self, monkeypatch):
        """Development mode should honour KAVACH_DEVELOPMENT_ACTOR_ID."""
        monkeypatch.setenv("KAVACH_DEVELOPMENT_ACTOR_ID", "custom-dev-actor")
        monkeypatch.delenv("KAVACH_DEVELOPMENT_ACTOR_NAME", raising=False)

        actor_id, actor_name = _resolve_bootstrap_administrator(
            "development",
            organization_id="test",
            organization_name="Test",
            organization_slug="test",
            project_id="test",
            project_name="Test",
            project_slug="test",
        )

        assert actor_id == "custom-dev-actor"
        assert actor_name == "Local Administrator"

    def test_honours_development_actor_name(self, monkeypatch):
        """Development mode should honour KAVACH_DEVELOPMENT_ACTOR_NAME."""
        monkeypatch.delenv("KAVACH_DEVELOPMENT_ACTOR_ID", raising=False)
        monkeypatch.setenv(
            "KAVACH_DEVELOPMENT_ACTOR_NAME", "Custom Developer Name"
        )

        actor_id, actor_name = _resolve_bootstrap_administrator(
            "development",
            organization_id="test",
            organization_name="Test",
            organization_slug="test",
            project_id="test",
            project_name="Test",
            project_slug="test",
        )

        assert actor_id == "local-admin"
        assert actor_name == "Custom Developer Name"


# ---------------------------------------------------------------------------
# _resolve_bootstrap_administrator — keycloak mode
# ---------------------------------------------------------------------------

class TestResolveBootstrapAdminKeycloakMode:
    def test_uses_bootstrap_admin_sub(self, monkeypatch):
        """Keycloak mode should use KAVACH_BOOTSTRAP_ADMIN_SUB."""
        monkeypatch.setenv(
            "KAVACH_BOOTSTRAP_ADMIN_SUB", "1d992555-b7a4-407e-a191-b3b779b7663f"
        )
        monkeypatch.delenv("KAVACH_BOOTSTRAP_ADMIN_NAME", raising=False)

        actor_id, actor_name = _resolve_bootstrap_administrator(
            "keycloak",
            organization_id="test",
            organization_name="Test",
            organization_slug="test",
            project_id="test",
            project_name="Test",
            project_slug="test",
        )

        assert actor_id == "1d992555-b7a4-407e-a191-b3b779b7663f"
        assert actor_name is None

    def test_honours_bootstrap_admin_name(self, monkeypatch):
        """Keycloak mode should honour KAVACH_BOOTSTRAP_ADMIN_NAME."""
        monkeypatch.setenv(
            "KAVACH_BOOTSTRAP_ADMIN_SUB", "1d992555-b7a4-407e-a191-b3b779b7663f"
        )
        monkeypatch.setenv(
            "KAVACH_BOOTSTRAP_ADMIN_NAME", "Keycloak Admin User"
        )

        actor_id, actor_name = _resolve_bootstrap_administrator(
            "keycloak",
            organization_id="test",
            organization_name="Test",
            organization_slug="test",
            project_id="test",
            project_name="Test",
            project_slug="test",
        )

        assert actor_id == "1d992555-b7a4-407e-a191-b3b779b7663f"
        assert actor_name == "Keycloak Admin User"

    def test_fails_when_bootstrap_admin_sub_missing(self, monkeypatch):
        """Keycloak mode should fail when KAVACH_BOOTSTRAP_ADMIN_SUB is absent."""
        monkeypatch.delenv("KAVACH_BOOTSTRAP_ADMIN_SUB", raising=False)
        monkeypatch.delenv("KAVACH_BOOTSTRAP_ADMIN_NAME", raising=False)

        with pytest.raises(ValueError, match="KAVACH_BOOTSTRAP_ADMIN_SUB is required"):
            _resolve_bootstrap_administrator(
                "keycloak",
                organization_id="test",
                organization_name="Test",
                organization_slug="test",
                project_id="test",
                project_name="Test",
                project_slug="test",
            )


# ---------------------------------------------------------------------------
# _resolve_bootstrap_administrator — invalid mode
# ---------------------------------------------------------------------------

class TestResolveBootstrapAdminInvalidMode:
    def test_raises_value_error_for_unknown_mode(self):
        """Should raise ValueError for unsupported auth modes."""
        with pytest.raises(ValueError, match="Unsupported authentication mode"):
            _resolve_bootstrap_administrator(
                "unknown",
                organization_id="test",
                organization_name="Test",
                organization_slug="test",
                project_id="test",
                project_name="Test",
                project_slug="test",
            )


# ---------------------------------------------------------------------------
# bootstrap_control_plane — idempotency
# ---------------------------------------------------------------------------

class TestBootstrapControlPlaneIdempotency:
    def test_skips_when_organization_exists(self):
        """Bootstrap should skip when the organization already exists."""
        repo = MagicMock()
        # Simulate organization already existing by returning it
        existing_org = Organization(
            organization_id="org_test",
            name="Test Organization",
            slug="test-org",
            status=OrganizationStatus.ACTIVE,
            created_at=MagicMock(),
            updated_at=MagicMock(),
        )
        repo.get_organization.return_value = existing_org

        bootstrap_control_plane(
            repo,
            organization_id="org_test",
            organization_name="Test Organization",
            organization_slug="test-org",
            project_id="proj_test",
            project_name="Test Project",
            project_slug="test-proj",
            auth_mode="development",
        )

        # Verify no create calls were made — bootstrap skipped
        repo.create_organization.assert_not_called()
        repo.create_membership.assert_not_called()
        repo.create_assignment.assert_not_called()
        repo.create_project.assert_not_called()

    def test_bootstrap_creates_organization_and_project(self, monkeypatch):
        """Bootstrap should create organization and project when they don't exist."""
        monkeypatch.setenv("KAVACH_AUTH_MODE", "development")
        monkeypatch.delenv("KAVACH_DEVELOPMENT_ACTOR_ID", raising=False)
        monkeypatch.delenv("KAVACH_DEVELOPMENT_ACTOR_NAME", raising=False)

        repo = _make_bootstrap_repository(actor_id="local-admin")

        # Mock AuthorizationService.authorize to always allow — we're testing
        # bootstrap logic, not authorization logic.
        with patch(
            "kavach.tenancy.services.AuthorizationService.authorize"
        ) as mock_authorize:
            from kavach.tenancy.authorization import AuthorizationDecision

            mock_authorize.return_value = AuthorizationDecision(
                allowed=True, permission=None, matched_roles=(), reason_code=None
            )

            bootstrap_control_plane(
                repo,
                organization_id="org_test",
                organization_name="Test Organization",
                organization_slug="test-org",
                project_id="proj_test",
                project_name="Test Project",
                project_slug="test-proj",
                auth_mode="development",
            )

            # Verify organization was created
            repo.create_organization.assert_called_once()

            # Verify membership was created
            repo.create_membership.assert_called_once()

            # Verify assignment was created
            repo.create_assignment.assert_called_once()

            # Verify project was created
            repo.create_project.assert_called_once()


# ---------------------------------------------------------------------------
# bootstrap_control_plane — keycloak mode integration
# ---------------------------------------------------------------------------

class TestBootstrapControlPlaneKeycloakMode:
    def test_uses_bootstrap_admin_sub_in_keycloak_mode(self, monkeypatch):
        """Bootstrap in keycloak mode should use KAVACH_BOOTSTRAP_ADMIN_SUB."""
        monkeypatch.setenv("KAVACH_AUTH_MODE", "keycloak")
        monkeypatch.setenv(
            "KAVACH_BOOTSTRAP_ADMIN_SUB", "kc-user-sub-123"
        )
        monkeypatch.setenv(
            "KAVACH_BOOTSTRAP_ADMIN_NAME", "KC Admin"
        )

        repo = _make_bootstrap_repository(actor_id="kc-user-sub-123")

        # Mock AuthorizationService.authorize to always allow
        with patch(
            "kavach.tenancy.services.AuthorizationService.authorize"
        ) as mock_authorize:
            from kavach.tenancy.authorization import AuthorizationDecision

            mock_authorize.return_value = AuthorizationDecision(
                allowed=True, permission=None, matched_roles=(), reason_code=None
            )

            bootstrap_control_plane(
                repo,
                organization_id="org_test",
                organization_name="Test Organization",
                organization_slug="test-org",
                project_id="proj_test",
                project_name="Test Project",
                project_slug="test-proj",
                auth_mode="keycloak",
            )

            # Verify membership was created with the correct actor_id
            repo.create_membership.assert_called_once()
            membership_call = repo.create_membership.call_args[0][0]
            assert membership_call.actor_id == "kc-user-sub-123"

    def test_fails_when_bootstrap_admin_sub_missing_in_keycloak_mode(self, monkeypatch):
        """Bootstrap in keycloak mode should fail when KAVACH_BOOTSTRAP_ADMIN_SUB is missing."""
        monkeypatch.setenv("KAVACH_AUTH_MODE", "keycloak")
        monkeypatch.delenv("KAVACH_BOOTSTRAP_ADMIN_SUB", raising=False)

        repo = _make_repository()

        with pytest.raises(ValueError, match="KAVACH_BOOTSTRAP_ADMIN_SUB is required"):
            bootstrap_control_plane(
                repo,
                organization_id="org_test",
                organization_name="Test Organization",
                organization_slug="test-org",
                project_id="proj_test",
                project_name="Test Project",
                project_slug="test-proj",
                auth_mode="keycloak",
            )


# ---------------------------------------------------------------------------
# bootstrap_control_plane — idempotency verification
# ---------------------------------------------------------------------------

class TestBootstrapControlPlaneIdempotencyVerification:
    def test_skips_when_organization_already_exists(self):
        """Bootstrap should skip when the organization already exists."""
        repo = MagicMock()
        # Simulate organization already existing by returning it
        existing_org = Organization(
            organization_id="org_test",
            name="Test Organization",
            slug="test-org",
            status=OrganizationStatus.ACTIVE,
            created_at=MagicMock(),
            updated_at=MagicMock(),
        )
        repo.get_organization.return_value = existing_org

        bootstrap_control_plane(
            repo,
            organization_id="org_test",
            organization_name="Test Organization",
            organization_slug="test-org",
            project_id="proj_test",
            project_name="Test Project",
            project_slug="test-proj",
            auth_mode="development",
        )

        # Verify no create calls were made — bootstrap skipped
        repo.create_organization.assert_not_called()
        repo.create_membership.assert_not_called()
        repo.create_assignment.assert_not_called()
        repo.create_project.assert_not_called()
