from __future__ import annotations

from ai_governance.tenancy.authorization import AuthorizationService
from ai_governance.tenancy.domain import BuiltInRole, TenantContext
from ai_governance.tenancy.permissions import Permission
from ai_governance.tenancy.repository import InMemoryControlPlaneRepository
from ai_governance.tenancy.services import (
    bootstrap_control_plane,
    provision_causal_audit_validator_service_account,
    provision_external_runtime_service_account,
)


def _repository() -> InMemoryControlPlaneRepository:
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
    return repository


def test_external_runtime_account_is_project_scoped_and_least_privilege() -> None:
    repository = _repository()
    provision_external_runtime_service_account(
        repository,
        organization_id="org_default",
        project_id="project_default",
        actor_id="runtime-subject",
    )

    assignments = repository.list_assignments("org_default", "runtime-subject")
    assert [(item.project_id, item.role) for item in assignments] == [
        ("project_default", BuiltInRole.EXTERNAL_RUNTIME_OPERATOR)
    ]
    authorization = AuthorizationService(repository)
    allowed = authorization.authorize(
        TenantContext("org_default", "project_default", "runtime-subject", "request"),
        Permission.AGENT_EXECUTION_INGEST,
    )
    denied = authorization.authorize(
        TenantContext("org_default", "project_default", "runtime-subject", "request"),
        Permission.SETTINGS_MANAGE,
    )
    cross_project = authorization.authorize(
        TenantContext("org_default", "other-project", "runtime-subject", "request"),
        Permission.AGENT_EXECUTION_INGEST,
    )
    assert allowed.allowed is True
    assert denied.allowed is False
    assert cross_project.allowed is False


def test_optional_test_role_replaces_the_normal_runtime_role() -> None:
    repository = _repository()
    arguments = {
        "organization_id": "org_default",
        "project_id": "project_default",
        "actor_id": "runtime-subject",
    }
    provision_external_runtime_service_account(repository, **arguments)
    provision_external_runtime_service_account(
        repository, **arguments, grant_test_settings_manage=True
    )

    assignments = repository.list_assignments("org_default", "runtime-subject")
    assert [item.role for item in assignments] == [
        BuiltInRole.EXTERNAL_RUNTIME_TEST_OPERATOR
    ]


def test_causal_audit_validator_is_a_distinct_project_scoped_operator() -> None:
    repository = _repository()
    provision_causal_audit_validator_service_account(
        repository,
        organization_id="org_default",
        project_id="project_default",
        actor_id="validator-subject",
    )

    assignments = repository.list_assignments("org_default", "validator-subject")
    assert [(item.project_id, item.role) for item in assignments] == [
        ("project_default", BuiltInRole.EXTERNAL_RUNTIME_OPERATOR)
    ]
    authorization = AuthorizationService(repository)
    assert authorization.authorize(
        TenantContext("org_default", "project_default", "validator-subject", "request"),
        Permission.CAUSAL_AUDIT_CREATE,
    ).allowed is True
    assert authorization.authorize(
        TenantContext("org_default", "project_default", "validator-subject", "request"),
        Permission.JOB_SUBMIT,
    ).allowed is True
    assert authorization.authorize(
        TenantContext("org_default", "other-project", "validator-subject", "request"),
        Permission.CAUSAL_AUDIT_CREATE,
    ).allowed is False
