from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MCPRequest(BaseModel):
    """
    Base class for MCP tool input DTOs.
    """

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", check_fields=False)
    @classmethod
    def string_must_not_be_blank(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class MCPContext(MCPRequest):
    organization_id: str = Field(min_length=1)
    project_id: str | None = None


class TenantRequest(MCPRequest):
    context: MCPContext


class ControlledTenantWriteRequest(TenantRequest):
    request_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    dry_run: bool = False


class OrganizationListRequest(TenantRequest):
    pass


class OrganizationGetRequest(TenantRequest):
    organization_id: str = Field(min_length=1)


class ProjectListRequest(TenantRequest):
    pass


class ProjectGetRequest(TenantRequest):
    project_id: str = Field(min_length=1)


class MembershipListRequest(TenantRequest):
    pass


class RoleAssignmentListRequest(TenantRequest):
    pass


class AuthorizationPermissionsRequest(TenantRequest):
    actor_id: str = Field(min_length=1)


class OrganizationCreateToolRequest(ControlledTenantWriteRequest):
    organization_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)


class OrganizationUpdateToolRequest(ControlledTenantWriteRequest):
    name: str | None = None
    slug: str | None = None


class ProjectCreateToolRequest(ControlledTenantWriteRequest):
    project_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    description: str | None = None


class ProjectUpdateToolRequest(ControlledTenantWriteRequest):
    project_id: str = Field(min_length=1)
    name: str | None = None
    slug: str | None = None
    description: str | None = None


class MembershipAddToolRequest(ControlledTenantWriteRequest):
    actor_id: str = Field(min_length=1)
    display_name: str | None = None


class MembershipUpdateToolRequest(ControlledTenantWriteRequest):
    actor_id: str = Field(min_length=1)
    status: str = Field(min_length=1)


class RoleAssignmentAssignToolRequest(ControlledTenantWriteRequest):
    actor_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    project_id: str | None = None


class RoleAssignmentRemoveToolRequest(ControlledTenantWriteRequest):
    assignment_id: str = Field(min_length=1)


class SettingsListRequest(TenantRequest):
    category: str | None = None
    scope: Literal["SYSTEM", "ORGANIZATION", "PROJECT"] = "SYSTEM"


class SettingsGetRequest(TenantRequest):
    key: str = Field(min_length=1)
    scope: Literal["SYSTEM", "ORGANIZATION", "PROJECT"] = "SYSTEM"


class SettingsUpdateRequest(ControlledTenantWriteRequest):
    key: str = Field(min_length=1)
    value: Any
    scope: Literal["SYSTEM", "ORGANIZATION", "PROJECT"] = "SYSTEM"
    expected_version: int = Field(ge=0)


class SettingsValidateRequest(ControlledTenantWriteRequest):
    key: str = Field(min_length=1)
    value: Any


class EmptyRequest(MCPRequest):
    """
    Input for tools that do not accept parameters.
    """


class WriteEnvelope(MCPRequest):
    """
    Shared envelope for controlled MCP write operations.
    """

    request_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    actor_type: Literal["HUMAN", "AGENT", "SERVICE"]
    reason: str = Field(min_length=1)
    dry_run: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    agent_name: str | None = None
    agent_session_id: str | None = None
    client_name: str | None = None
    client_version: str | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)
    context: MCPContext | None = None

    def audit_metadata(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "agent_name": self.agent_name,
            "agent_session_id": self.agent_session_id,
            "client_name": self.client_name,
            "client_version": self.client_version,
        }

    def submitted_by(self) -> str:
        return self.requested_by


class ReplayGetRequest(TenantRequest):
    replay_id: str = Field(min_length=1)


class ReplayListRequest(TenantRequest):
    status: str | None = None
    source_execution_id: str | None = None
    requested_by: str | None = None
    limit: int = Field(default=100, ge=1, le=200)

    def to_query_params(self) -> dict[str, Any]:
        return self.model_dump(exclude={"context"}, exclude_none=True)


class ReplayCreateToolRequest(WriteEnvelope):
    source_execution_id: str = Field(min_length=1)
    mode: str = "FULL"
    configuration_source: str = "ORIGINAL"


class ReplayArchiveToolRequest(WriteEnvelope):
    replay_id: str = Field(min_length=1)


class ReplaySubmitToolRequest(WriteEnvelope):
    replay_id: str = Field(min_length=1)


class ReplayCancelToolRequest(WriteEnvelope):
    replay_id: str = Field(min_length=1)


class ReplayEvaluateToolRequest(WriteEnvelope):
    replay_id: str = Field(min_length=1)
    baseline_strategy: str = "LATEST_COMPATIBLE"
    baseline_evaluation_id: str | None = None
    evaluation_provider: str | None = None


class ReplayResultRequest(TenantRequest):
    replay_id: str = Field(min_length=1)


class PromptGetRequest(MCPRequest):
    prompt_name: str = Field(min_length=1)


class ModelGetRequest(MCPRequest):
    model_id: str = Field(min_length=1)


class DatasetGetRequest(MCPRequest):
    dataset_id: str = Field(min_length=1)


class OntologyGraphEntityRequest(MCPRequest):
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)


class OntologyGraphRelationshipRequest(MCPRequest):
    relationship_id: str = Field(min_length=1)


class OntologyGraphRelationshipsRequest(OntologyGraphEntityRequest):
    direction: str | None = None
    relationship_type: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    cursor: str | None = None

    def to_query_params(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "relationship_type": self.relationship_type,
            "limit": self.limit,
            "cursor": self.cursor,
        }


class OntologyGraphTraversalRequest(OntologyGraphEntityRequest):
    depth: int = Field(default=1, ge=1, le=5)
    relationship_type: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=500)

    def to_query_params(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "relationship_type": self.relationship_type,
            "limit": self.limit,
        }


class OntologyGraphNeighbourhoodRequest(OntologyGraphTraversalRequest):
    entity_type_filter: list[str] = Field(default_factory=list)

    def to_query_params(self) -> dict[str, Any]:
        params = super().to_query_params()
        params["entity_type"] = self.entity_type_filter
        return params


class OntologyGraphPathRequest(MCPRequest):
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    max_depth: int = Field(default=5, ge=1, le=5)
    relationship_type: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=500)

    def to_query_params(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "max_depth": self.max_depth,
            "relationship_type": self.relationship_type,
            "limit": self.limit,
        }


class EvaluationHistoryRequest(MCPRequest):
    execution_id: str = Field(min_length=1)


class EvaluationLatestRequest(MCPRequest):
    execution_id: str = Field(min_length=1)


class EvaluationGetRequest(MCPRequest):
    evaluation_id: str = Field(min_length=1)


class EvaluationSubmitAsyncRequest(WriteEnvelope):
    provider_name: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    execution_id: str = Field(min_length=1)
    workflow_name: str | None = None
    workflow_version: str | None = None
    execution_status: str = Field(min_length=1)
    input: dict[str, Any]
    final_state: dict[str, Any]
    events: list[dict[str, Any]] = Field(default_factory=list)
    metric_specs: list[dict[str, Any]] = Field(default_factory=list)
    provider_config: dict[str, Any] = Field(default_factory=dict)


class ExperimentGetRequest(MCPRequest):
    experiment_id: str = Field(min_length=1)


class ExperimentCandidatesRequest(MCPRequest):
    experiment_id: str = Field(min_length=1)


class ExperimentRunsRequest(MCPRequest):
    experiment_id: str = Field(min_length=1)


class ExperimentComparisonRequest(MCPRequest):
    experiment_id: str = Field(min_length=1)
    baseline_candidate_id: str = Field(min_length=1)
    comparison_candidate_id: str = Field(min_length=1)

    def to_query_params(self) -> dict[str, Any]:
        return {
            "baseline_candidate_id": self.baseline_candidate_id,
            "comparison_candidate_id": self.comparison_candidate_id,
        }


class ExperimentLeaderboardRequest(MCPRequest):
    experiment_id: str = Field(min_length=1)


class ExperimentCreateRequest(WriteEnvelope):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ExperimentAddCandidateRequest(WriteEnvelope):
    experiment_id: str = Field(min_length=1)
    candidate_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    runtime_parameters: dict[str, Any] = Field(default_factory=dict)
    candidate_metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentRunAsyncRequest(WriteEnvelope):
    experiment_id: str = Field(min_length=1)
    metric_specs: list[dict[str, Any]] = Field(default_factory=list)
    provider_config: dict[str, Any] = Field(default_factory=dict)


class GovernanceCompareRequest(MCPRequest):
    baseline_evaluation_id: str = Field(min_length=1)
    candidate_evaluation_id: str = Field(min_length=1)


class GovernanceDriftRequest(MCPRequest):
    baseline_evaluation_id: str = Field(min_length=1)
    candidate_evaluation_id: str = Field(min_length=1)


class GovernanceReportRequest(MCPRequest):
    evaluation_id: str = Field(min_length=1)


class GovernanceDecisionEvaluateRequest(MCPRequest):
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    policy_ids: list[str] = Field(default_factory=list)
    correlation_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernanceDecisionGetRequest(MCPRequest):
    decision_id: str = Field(min_length=1)


class GovernanceDecisionListRequest(MCPRequest):
    target_type: str | None = None
    target_id: str | None = None
    status: str | None = None
    correlation_id: str | None = None
    limit: int = Field(default=50, ge=1, le=500)

    def to_query_params(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "status": self.status,
            "correlation_id": self.correlation_id,
            "limit": self.limit,
        }


class GovernanceDecisionLineageRequest(GovernanceDecisionGetRequest):
    depth: int = Field(default=2, ge=1, le=5)

    def to_query_params(self) -> dict[str, Any]:
        return {"depth": self.depth}


class ExperimentInsightRequest(MCPRequest):
    experiment_id: str = Field(min_length=1)


class CandidateInsightRequest(MCPRequest):
    experiment_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)


class InvestigationCorrelationRequest(MCPRequest):
    correlation_id: str = Field(min_length=1)


class InvestigationAuditRequest(MCPRequest):
    audit_id: str = Field(min_length=1)


class DriftExplanationRequest(MCPRequest):
    drift_id: str = Field(min_length=1)


class ReportFormatRequest(MCPRequest):
    format: Literal["json", "markdown"] = "json"

    def to_query_params(self) -> dict[str, Any]:
        return {"format": self.format}


class ExperimentReportRequest(ReportFormatRequest):
    experiment_id: str = Field(min_length=1)


class EvaluationReportRequest(ReportFormatRequest):
    evaluation_id: str = Field(min_length=1)


class DriftReportRequest(ReportFormatRequest):
    drift_id: str = Field(min_length=1)


class InvestigationReportRequest(ReportFormatRequest):
    correlation_id: str = Field(min_length=1)


class JobListRequest(MCPRequest):
    status: str | None = None
    job_type: str | None = None
    limit: int = Field(default=100, ge=1, le=500)

    def to_query_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": self.limit}
        if self.status is not None:
            params["status"] = self.status
        if self.job_type is not None:
            params["job_type"] = self.job_type
        return params


class JobStatusRequest(MCPRequest):
    job_id: str = Field(min_length=1)


class JobMutationRequest(WriteEnvelope):
    job_id: str = Field(min_length=1)


class MCPAuditListRequest(MCPRequest):
    request_id: str | None = None
    correlation_id: str | None = None
    tool_name: str | None = None
    status: str | None = None
    actor_id: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    interrupted_after_seconds: int = Field(default=3600, ge=1)

    def to_query_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": self.limit,
            "interrupted_after_seconds": self.interrupted_after_seconds,
        }
        if self.request_id is not None:
            params["request_id"] = self.request_id
        if self.correlation_id is not None:
            params["correlation_id"] = self.correlation_id
        if self.tool_name is not None:
            params["tool_name"] = self.tool_name
        if self.status is not None:
            params["status"] = self.status
        if self.actor_id is not None:
            params["actor_id"] = self.actor_id
        return params


class MCPAuditGetRequest(MCPRequest):
    audit_id: str = Field(min_length=1)
    interrupted_after_seconds: int = Field(default=3600, ge=1)

    def to_query_params(self) -> dict[str, Any]:
        return {
            "interrupted_after_seconds": self.interrupted_after_seconds,
        }


class MCPAuditFindByRequestRequest(MCPRequest):
    request_id: str = Field(min_length=1)
    interrupted_after_seconds: int = Field(default=3600, ge=1)

    def to_query_params(self) -> dict[str, Any]:
        return {
            "interrupted_after_seconds": self.interrupted_after_seconds,
        }


class MCPAuditFindByCorrelationRequest(MCPRequest):
    correlation_id: str = Field(min_length=1)
    interrupted_after_seconds: int = Field(default=3600, ge=1)

    def to_query_params(self) -> dict[str, Any]:
        return {
            "interrupted_after_seconds": self.interrupted_after_seconds,
        }
