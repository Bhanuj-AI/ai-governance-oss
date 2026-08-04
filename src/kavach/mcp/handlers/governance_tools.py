from __future__ import annotations

from kavach.mcp.clients import RestClient
from kavach.mcp.dto import (
    CandidateInsightRequest,
    DriftExplanationRequest,
    DriftReportRequest,
    EvaluationGetRequest,
    EvaluationReportRequest,
    ExperimentInsightRequest,
    ExperimentReportRequest,
    GovernanceCompareRequest,
    GovernanceDecisionEvaluateRequest,
    GovernanceDecisionGetRequest,
    GovernanceDecisionLineageRequest,
    GovernanceDecisionListRequest,
    GovernanceDriftRequest,
    GovernanceReportRequest,
    InvestigationAuditRequest,
    InvestigationCorrelationRequest,
    InvestigationReportRequest,
    JobStatusRequest,
)
from kavach.mcp.handlers._rest_tool import rest_get, rest_post
from kavach.mcp.observability import MCPMetrics
from kavach.mcp.registry import ToolRegistry


def register_governance_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
) -> None:
    registry.register(
        name="governance.compare",
        description="Compare two persisted evaluations.",
        request_model=GovernanceCompareRequest,
        handler=lambda request: rest_post(
            rest_client,
            metrics,
            "/api/v1/governance/compare",
            body=request.model_dump(),
        ),
    )
    registry.register(
        name="governance.drift",
        description="Analyze governance drift between two evaluations.",
        request_model=GovernanceDriftRequest,
        handler=lambda request: rest_post(
            rest_client,
            metrics,
            "/api/v1/governance/drift",
            body=request.model_dump(),
        ),
    )
    registry.register(
        name="governance.report",
        description="Return a governance report by evaluation ID.",
        request_model=GovernanceReportRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/governance/reports/{request.evaluation_id}",
        ),
    )
    registry.register(
        name="governance_decision.evaluate",
        description="Evaluate and persist a governance decision.",
        request_model=GovernanceDecisionEvaluateRequest,
        handler=lambda request: rest_post(
            rest_client,
            metrics,
            "/api/v1/decisions/evaluate",
            body=request.model_dump(),
        ),
    )
    registry.register(
        name="governance_decision.get",
        description="Return a persisted governance decision.",
        request_model=GovernanceDecisionGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/decisions/{request.decision_id}",
        ),
    )
    registry.register(
        name="governance_decision.list",
        description="List governance decisions.",
        request_model=GovernanceDecisionListRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            "/api/v1/decisions",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="governance_decision.evidence",
        description="Return decision evidence references and rebuilt graph.",
        request_model=GovernanceDecisionGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/decisions/{request.decision_id}/evidence",
        ),
    )
    registry.register(
        name="governance_decision.explain",
        description="Return a persisted deterministic decision explanation.",
        request_model=GovernanceDecisionGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/decisions/{request.decision_id}/explanation",
        ),
    )
    registry.register(
        name="governance_decision.lineage",
        description="Return ontology lineage around a governance decision.",
        request_model=GovernanceDecisionLineageRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/decisions/{request.decision_id}/lineage",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="governance.summarize_experiment",
        description="Summarize experiment outcome evidence.",
        request_model=ExperimentInsightRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/experiments/{request.experiment_id}/insights",
        ),
    )
    registry.register(
        name="governance.explain_candidate",
        description="Explain one experiment candidate using evidence.",
        request_model=CandidateInsightRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            "/api/v1/experiments/"
            f"{request.experiment_id}/candidates/"
            f"{request.candidate_id}/insights",
        ),
    )
    registry.register(
        name="governance.compare_candidates",
        description="Compare experiment candidates using leaderboard evidence.",
        request_model=ExperimentInsightRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/experiments/{request.experiment_id}/comparative-insights",
        ),
    )
    registry.register(
        name="governance.investigate_execution",
        description="Investigate execution evidence by correlation ID.",
        request_model=InvestigationCorrelationRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/investigations/by-correlation/{request.correlation_id}",
        ),
    )
    registry.register(
        name="governance.investigate_job",
        description="Investigate execution evidence by job ID.",
        request_model=JobStatusRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/investigations/by-job/{request.job_id}",
        ),
    )
    registry.register(
        name="governance.investigate_evaluation",
        description="Investigate execution evidence by evaluation ID.",
        request_model=EvaluationGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/investigations/by-evaluation/{request.evaluation_id}",
        ),
    )
    registry.register(
        name="governance.investigate_audit",
        description="Investigate execution evidence by MCP audit ID.",
        request_model=InvestigationAuditRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/investigations/by-audit/{request.audit_id}",
        ),
    )
    registry.register(
        name="governance.explain_drift",
        description="Explain a drift identifier using governance evidence.",
        request_model=DriftExplanationRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/governance/drift/{request.drift_id}/explanation",
        ),
    )
    registry.register(
        name="governance.summarize_drift",
        description="Summarize drift for an evaluation.",
        request_model=EvaluationGetRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/evaluations/{request.evaluation_id}/drift-explanation",
        ),
    )
    registry.register(
        name="governance.generate_experiment_report",
        description="Generate an experiment evidence report.",
        request_model=ExperimentReportRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/reports/experiments/{request.experiment_id}",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="governance.generate_evaluation_report",
        description="Generate an evaluation evidence report.",
        request_model=EvaluationReportRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/reports/evaluations/{request.evaluation_id}",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="governance.generate_drift_report",
        description="Generate a drift evidence report.",
        request_model=DriftReportRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/reports/drift/{request.drift_id}",
            query=request.to_query_params(),
        ),
    )
    registry.register(
        name="governance.generate_investigation_report",
        description="Generate an execution investigation evidence report.",
        request_model=InvestigationReportRequest,
        handler=lambda request: rest_get(
            rest_client,
            metrics,
            f"/api/v1/reports/investigations/{request.correlation_id}",
            query=request.to_query_params(),
        ),
    )
