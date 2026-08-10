from __future__ import annotations

from ai_governance.tenancy.domain import BuiltInRole, RoleAssignment, utcnow
from ai_governance.tenancy.repository import InMemoryControlPlaneRepository
from ai_governance.tenancy.services import (
    bootstrap_control_plane,
    provision_walkthrough_service_account,
)


def test_walkthrough_service_account_receives_idempotent_tenant_membership() -> None:
    repository = InMemoryControlPlaneRepository()
    bootstrap_control_plane(
        repository,
        organization_id="org_default",
        organization_name="Default Organization",
        organization_slug="default",
        project_id="project_default",
        project_name="Default Project",
        project_slug="default",
    )

    provision_walkthrough_service_account(
        repository, organization_id="org_default", actor_id="walkthrough-subject"
    )
    provision_walkthrough_service_account(
        repository, organization_id="org_default", actor_id="walkthrough-subject"
    )

    membership = repository.get_membership("org_default", "walkthrough-subject")
    assignments = repository.list_assignments(
        "org_default", actor_id="walkthrough-subject"
    )
    assert membership.display_name == "AI Governance Control Plane walkthrough service account"
    assert [assignment.role for assignment in assignments] == [
        BuiltInRole.GOVERNANCE_ADMIN
    ]


def test_walkthrough_service_account_replaces_its_legacy_operator_assignment() -> None:
    repository = InMemoryControlPlaneRepository()
    bootstrap_control_plane(
        repository,
        organization_id="org_default",
        organization_name="Default Organization",
        organization_slug="default",
        project_id="project_default",
        project_name="Default Project",
        project_slug="default",
    )
    provision_walkthrough_service_account(
        repository, organization_id="org_default", actor_id="walkthrough-subject"
    )
    repository.create_assignment(
        RoleAssignment(
            "role_walkthrough_walkthroughsubject",
            "org_default",
            None,
            "walkthrough-subject",
            BuiltInRole.PLATFORM_OPERATOR,
            utcnow(),
            "walkthrough-subject",
        )
    )

    provision_walkthrough_service_account(
        repository, organization_id="org_default", actor_id="walkthrough-subject"
    )

    assert [
        assignment.role
        for assignment in repository.list_assignments(
            "org_default", actor_id="walkthrough-subject"
        )
    ] == [BuiltInRole.GOVERNANCE_ADMIN]
