from __future__ import annotations

from enum import Enum
from types import MappingProxyType

from .domain import BuiltInRole


PERMISSION_MODEL_VERSION = "1"


class Permission(str, Enum):
    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_UPDATE = "organization.update"
    PROJECT_CREATE = "project.create"
    PROJECT_READ = "project.read"
    PROJECT_UPDATE = "project.update"
    PROJECT_ARCHIVE = "project.archive"
    MEMBERSHIP_READ = "membership.read"
    MEMBERSHIP_MANAGE = "membership.manage"
    ROLE_ASSIGNMENT_READ = "role_assignment.read"
    ROLE_ASSIGNMENT_MANAGE = "role_assignment.manage"
    POLICY_CREATE = "policy.create"
    POLICY_READ = "policy.read"
    POLICY_UPDATE = "policy.update"
    POLICY_VALIDATE = "policy.validate"
    POLICY_SIMULATE = "policy.simulate"
    POLICY_REVIEW = "policy.review"
    POLICY_PUBLISH = "policy.publish"
    POLICY_DEPRECATE = "policy.deprecate"
    DECISION_EVALUATE = "decision.evaluate"
    DECISION_READ = "decision.read"
    DECISION_EXPLAIN = "decision.explain"
    EVALUATION_EXECUTE = "evaluation.execute"
    EVALUATION_READ = "evaluation.read"
    JOB_SUBMIT = "job.submit"
    JOB_READ = "job.read"
    JOB_CANCEL = "job.cancel"
    JOB_RETRY = "job.retry"
    ONTOLOGY_READ = "ontology.read"
    ONTOLOGY_SYNCHRONIZE = "ontology.synchronize"
    ONTOLOGY_RECONCILE = "ontology.reconcile"
    AUDIT_READ = "audit.read"
    MCP_AUDIT_READ = "mcp_audit.read"
    PLATFORM_HEALTH_READ = "platform_health.read"
    ASSET_MANAGE = "asset.manage"
    RUNTIME_CONNECTION_MANAGE = "runtime_connection.manage"
    SETTINGS_READ = "settings.read"
    SETTINGS_MANAGE = "settings.manage"
    REPLAY_READ = "replay.read"
    REPLAY_CREATE = "replay.create"
    REPLAY_ARCHIVE = "replay.archive"
    REPLAY_EXECUTE = "replay.execute"
    REPLAY_CANCEL = "replay.cancel"
    REPLAY_EVALUATE = "replay.evaluate"
    REPLAY_RESULT_READ = "replay.result.read"
    ENTERPRISE_RECOMMENDATIONS_READ = "enterprise.recommendations.read"
    ENTERPRISE_RECOMMENDATIONS_SYNTHESIZE = "enterprise.recommendations.synthesize"


_viewer = frozenset(
    {
        Permission.POLICY_READ,
        Permission.DECISION_READ,
        Permission.DECISION_EXPLAIN,
        Permission.EVALUATION_READ,
        Permission.JOB_READ,
        Permission.ONTOLOGY_READ,
        Permission.AUDIT_READ,
        Permission.PLATFORM_HEALTH_READ,
        Permission.SETTINGS_READ,
        Permission.REPLAY_READ,
        Permission.REPLAY_RESULT_READ,
        Permission.ENTERPRISE_RECOMMENDATIONS_READ,
    }
)
_reviewer = _viewer | {Permission.POLICY_REVIEW, Permission.POLICY_PUBLISH}
_operator = frozenset(
    {
        Permission.JOB_SUBMIT,
        Permission.JOB_READ,
        Permission.JOB_CANCEL,
        Permission.JOB_RETRY,
        Permission.EVALUATION_EXECUTE,
        Permission.EVALUATION_READ,
        Permission.ONTOLOGY_READ,
        Permission.ONTOLOGY_RECONCILE,
        Permission.PLATFORM_HEALTH_READ,
        Permission.MCP_AUDIT_READ,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_MANAGE,
        Permission.REPLAY_READ,
        Permission.ENTERPRISE_RECOMMENDATIONS_READ,
    }
)
_governance_admin = frozenset(
    {
        Permission.ASSET_MANAGE,
        Permission.RUNTIME_CONNECTION_MANAGE,
        Permission.POLICY_CREATE,
        Permission.POLICY_READ,
        Permission.POLICY_UPDATE,
        Permission.POLICY_VALIDATE,
        Permission.POLICY_SIMULATE,
        Permission.POLICY_REVIEW,
        Permission.POLICY_PUBLISH,
        Permission.POLICY_DEPRECATE,
        Permission.DECISION_EVALUATE,
        Permission.DECISION_READ,
        Permission.DECISION_EXPLAIN,
        Permission.EVALUATION_EXECUTE,
        Permission.EVALUATION_READ,
        Permission.JOB_SUBMIT,
        Permission.JOB_READ,
        Permission.ONTOLOGY_READ,
        Permission.ONTOLOGY_SYNCHRONIZE,
        Permission.AUDIT_READ,
        Permission.SETTINGS_READ,
        Permission.REPLAY_READ,
        Permission.REPLAY_CREATE,
        Permission.REPLAY_ARCHIVE,
        Permission.REPLAY_EXECUTE,
        Permission.REPLAY_CANCEL,
        Permission.REPLAY_EVALUATE,
        Permission.REPLAY_RESULT_READ,
        Permission.SETTINGS_MANAGE,
        Permission.ENTERPRISE_RECOMMENDATIONS_READ,
        Permission.ENTERPRISE_RECOMMENDATIONS_SYNTHESIZE,
    }
)

ROLE_PERMISSIONS = MappingProxyType(
    {
        BuiltInRole.ORGANIZATION_ADMIN: frozenset(Permission),
        BuiltInRole.GOVERNANCE_ADMIN: _governance_admin,
        BuiltInRole.GOVERNANCE_REVIEWER: _reviewer,
        BuiltInRole.PLATFORM_OPERATOR: _operator,
        BuiltInRole.VIEWER: _viewer,
    }
)

_EXTENSION_PERMISSIONS: set[str] = set()

def register_extension_permissions(definitions) -> None:
    """Register generic plugin permissions; administrators receive them by default."""
    for definition in definitions:
        name = str(definition.name).strip()
        if not name or name in {item.value for item in Permission} or name in _EXTENSION_PERMISSIONS:
            raise ValueError(f"Permission '{name}' is already registered or invalid.")
        _EXTENSION_PERMISSIONS.add(name)

def role_permissions(role: BuiltInRole) -> frozenset[Permission | str]:
    base = ROLE_PERMISSIONS[role]
    return base | (frozenset(_EXTENSION_PERMISSIONS) if role is BuiltInRole.ORGANIZATION_ADMIN else frozenset())
