from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from ai_governance.authorization.contracts import (
    AuthorizationEnforcementRequest,
    AuthorizationEnforcer,
    AuthorizationResourceFacts,
)
from ai_governance.decisions import (
    DecisionAuditAction,
    DecisionAuditRecord,
    DecisionExplanation,
    DecisionStatus,
    DecisionTargetType,
    DecisionType,
    GovernanceDecision,
    GovernanceReasoningEngine,
    GovernanceReasoningOutcome,
    GovernanceReasoningRequest,
    ReasoningEvidenceSummary,
)
from ai_governance.decisions.evidence import DecisionEvidenceGraph, MissingEvidence
from ai_governance.decisions.evidence_builder import DecisionEvidenceBuilder
from ai_governance.decisions.exceptions import DecisionValidationError
from ai_governance.decisions.policies import PolicyEvaluationOutcome
from ai_governance.decisions.policy_enums import PolicyEffect
from ai_governance.decisions.validation import copy_mapping
from ai_governance.events import EventPublisher, ResourceLifecycleEvent
from ai_governance.ontology import EntityType, GraphSubgraph, OntologyGraphQueryService
from ai_governance.repositories.governance_decision_repository import (
    GovernanceDecisionRepository,
)
from ai_governance.settings_control.operational import duration_seconds, setting_context
from ai_governance.tenancy.domain import TenantContext

REQUEST_FINGERPRINT_METADATA_KEY = "_evaluate_request_fingerprint"
EVIDENCE_SUMMARY_METADATA_KEY = "_reasoning_evidence_summary"
POLICY_OUTCOMES_METADATA_KEY = "_policy_outcomes"
RECORDED_AT_METADATA_KEY = "_recorded_at"


class DecisionApplicationError(Exception):
    """
    Base class for decision application service errors.
    """


class DecisionNotFoundError(DecisionApplicationError):
    def __init__(self, decision_id: str) -> None:
        self.decision_id = decision_id
        super().__init__(f"Decision {decision_id!r} was not found.")


class InvalidDecisionRequestError(DecisionApplicationError):
    """
    Raised when the public decision request is invalid.
    """


class DecisionConflictError(DecisionApplicationError):
    """
    Raised when idempotency keys or decision IDs conflict.
    """


class PolicyNotFoundError(DecisionApplicationError):
    def __init__(self, policy_ids: Sequence[str]) -> None:
        self.policy_ids = tuple(policy_ids)
        super().__init__(
            "Decision policy was not found: " + ", ".join(sorted(self.policy_ids))
        )


class EvidenceUnavailableError(DecisionApplicationError):
    """
    Raised when decision evidence or explanation cannot be returned.
    """


class DecisionPersistenceFailedError(DecisionApplicationError):
    """
    Raised when the decision repository rejects or fails a write.
    """


class DecisionReasoningFailedError(DecisionApplicationError):
    """
    Raised when deterministic decision reasoning fails.
    """


@dataclass(frozen=True)
class DecisionEvaluateCommand:
    target_type: DecisionTargetType | str
    target_id: str
    decision_type: DecisionType | str
    policy_ids: Sequence[str] = ()
    correlation_id: str | None = None
    request_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context: TenantContext | None = None


@dataclass(frozen=True)
class DecisionEvaluationResult:
    decision: GovernanceDecision
    explanation: DecisionExplanation
    evidence_summary: ReasoningEvidenceSummary
    policy_outcomes: tuple[PolicyEvaluationOutcome, ...]


@dataclass(frozen=True)
class DecisionEvidenceResult:
    decision: GovernanceDecision
    evidence_graph: DecisionEvidenceGraph


@dataclass(frozen=True)
class DecisionLineageResult:
    decision: GovernanceDecision
    subgraph: GraphSubgraph


@dataclass(frozen=True)
class DecisionDetailResult:
    decision: GovernanceDecision
    evidence_summary: ReasoningEvidenceSummary
    policy_outcomes: tuple[PolicyEvaluationOutcome, ...]
    audit_records: tuple[DecisionAuditRecord, ...]


class GovernanceDecisionApplicationService:
    """
    Thin application service for REST and MCP decision workflows.
    """

    def __init__(
        self,
        reasoning_engine: GovernanceReasoningEngine,
        decision_repository: GovernanceDecisionRepository,
        evidence_builder: DecisionEvidenceBuilder,
        graph_query_service: OntologyGraphQueryService,
        configuration_service=None,
        event_publisher: EventPublisher | None = None,
        authorization_enforcers: tuple[AuthorizationEnforcer, ...] = (),
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._decision_repository = decision_repository
        self._evidence_builder = evidence_builder
        self._graph_query_service = graph_query_service
        self._configuration_service = configuration_service
        self._event_publisher = event_publisher
        self._authorization_enforcers = authorization_enforcers

    def evaluate(
        self,
        command: DecisionEvaluateCommand,
    ) -> DecisionEvaluationResult:
        try:
            request = GovernanceReasoningRequest(
                target_type=command.target_type,
                target_id=command.target_id,
                decision_type=command.decision_type,
                policy_ids=command.policy_ids,
                correlation_id=command.correlation_id,
                request_id=command.request_id,
                metadata=copy_mapping(command.metadata),
            )
        except DecisionValidationError as exc:
            raise InvalidDecisionRequestError(str(exc)) from exc

        self._enforce_evaluation_operation(command.context, request)

        request_fingerprint = _request_fingerprint(request)
        if request.request_id is not None:
            existing_by_request = self._decision_repository.find_by_request_id(
                request.request_id,
                limit=1,
            )
            if existing_by_request:
                return self._existing_result(
                    existing_by_request[0],
                    request_fingerprint,
                )

        outcome = self._reason(request)
        missing_policy_ids = tuple(
            sorted(
                set(request.policy_ids)
                - {outcome.policy_id for outcome in outcome.policy_outcomes}
            )
        )
        if missing_policy_ids:
            raise PolicyNotFoundError(missing_policy_ids)

        decision = _with_reasoning_metadata(
            outcome,
            request_fingerprint,
        )
        existing = self._decision_repository.get(decision.decision_id)
        if existing is not None:
            return self._existing_result(existing, request_fingerprint)

        try:
            self._decision_repository.save_with_explanation(
                decision,
                outcome.explanation,
            )
            self._decision_repository.save_audit(
                DecisionAuditRecord(
                    decision_id=decision.decision_id,
                    action=DecisionAuditAction.CREATED,
                    producer_id=decision.provenance.producer_id,
                    actor_id=decision.provenance.actor_id,
                    correlation_id=decision.provenance.correlation_id,
                    request_id=decision.provenance.request_id,
                    reason="Decision evaluated through public API.",
                )
            )
        except DecisionValidationError as exc:
            raise DecisionConflictError(str(exc)) from exc
        except Exception as exc:
            raise DecisionPersistenceFailedError(str(exc)) from exc

        self._publish_lifecycle_event(decision)

        return DecisionEvaluationResult(
            decision=decision,
            explanation=outcome.explanation,
            evidence_summary=outcome.evidence_summary,
            policy_outcomes=tuple(outcome.policy_outcomes),
        )

    def _publish_lifecycle_event(self, decision: GovernanceDecision) -> None:
        """Publish a generic fact once the decision and audit entry are durable."""
        if self._event_publisher is None:
            return
        organization_id = str(decision.metadata.get("_organization_id", "")).strip()
        if not organization_id:
            return
        project_id = str(decision.metadata.get("_project_id", "")).strip()
        payload = {
            "decision_type": decision.decision_type.value,
            "previous_state": "PROPOSED",
            "new_state": decision.status.value,
            "policy_references": [item.policy_id for item in decision.policies],
            "subject_resource": {
                "resource_type": decision.target.target_type.value,
                "resource_id": decision.target.target_id,
            },
            "actor_id": decision.provenance.actor_id,
            "reason": decision.reason,
            "decision_version": decision.metadata.get("version", 1),
            "request_id": decision.provenance.request_id,
        }
        states = ["created"]
        lifecycle_state = {
            DecisionStatus.APPROVED: "approved",
            DecisionStatus.REJECTED: "rejected",
            DecisionStatus.SUPERSEDED: "superseded",
            DecisionStatus.ARCHIVED: "archived",
        }.get(decision.status)
        if lifecycle_state is not None:
            states.append(lifecycle_state)
        for state in states:
            asyncio.run(
                self._event_publisher.publish(
                    ResourceLifecycleEvent(
                        tenant={
                            "organization_id": organization_id,
                            "project_id": project_id,
                        },
                        resource_kind="governance_decision",
                        resource_id=decision.decision_id,
                        state=state,
                        payload=payload,
                        correlation_id=decision.provenance.correlation_id,
                    )
                )
            )

    def get(
        self, decision_id: str, context: TenantContext | None = None
    ) -> GovernanceDecision:
        decision = self._decision_repository.get(decision_id)
        if decision is None or not _decision_in_context(decision, context):
            raise DecisionNotFoundError(decision_id)
        if self._configuration_service is not None:
            retention = duration_seconds(
                self._configuration_service.get(
                    "governance.decision_retention", setting_context(context)
                )
            )
            if (
                _decision_recorded_at(decision).timestamp()
                < datetime.now(UTC).timestamp() - retention
            ):
                raise DecisionNotFoundError(decision_id)
        return decision

    def detail(
        self, decision_id: str, context: TenantContext | None = None
    ) -> DecisionDetailResult:
        decision = self.get(decision_id, context)
        return DecisionDetailResult(
            decision=decision,
            evidence_summary=_evidence_summary_from_metadata(decision),
            policy_outcomes=_policy_outcomes_from_metadata(decision),
            audit_records=self._decision_repository.find_audit_by_decision(
                decision_id,
                limit=100,
            ),
        )

    def list(
        self,
        *,
        target_type: DecisionTargetType | None = None,
        target_id: str | None = None,
        status: DecisionStatus | None = None,
        correlation_id: str | None = None,
        limit: int = 50,
        context: TenantContext | None = None,
    ) -> tuple[GovernanceDecision, ...]:
        if (target_type is None) != (target_id is None):
            raise InvalidDecisionRequestError(
                "target_type and target_id must be provided together."
            )

        if correlation_id is not None:
            decisions = self._decision_repository.find_by_correlation_id(
                correlation_id,
                limit=limit,
            )
        elif target_type is not None and target_id is not None:
            decisions = self._decision_repository.find_by_target(
                target_type,
                target_id,
                limit=limit,
            )
        elif status is not None:
            decisions = self._decision_repository.find_by_status(
                status,
                limit=limit,
            )
        else:
            decisions = self._decision_repository.list(limit=limit)

        retention_cutoff = None
        if self._configuration_service is not None:
            retention_cutoff = datetime.now(UTC).timestamp() - duration_seconds(
                self._configuration_service.get(
                    "governance.decision_retention", setting_context(context)
                )
            )
        return tuple(
            decision
            for decision in decisions
            if _decision_in_context(decision, context)
            and (
                retention_cutoff is None
                or _decision_recorded_at(decision).timestamp() >= retention_cutoff
            )
            and (status is None or decision.status == status)
            and (target_type is None or decision.target.target_type == target_type)
            and (target_id is None or decision.target.target_id == target_id)
            and (
                correlation_id is None
                or decision.provenance.correlation_id == correlation_id
            )
        )[:limit]

    def evidence(
        self, decision_id: str, context: TenantContext | None = None
    ) -> DecisionEvidenceResult:
        decision = self.get(decision_id, context)
        try:
            evidence_graph = self._evidence_builder.build_for_target(
                decision.target.target_type,
                decision.target.target_id,
            )
        except Exception as exc:
            raise EvidenceUnavailableError(str(exc)) from exc
        return DecisionEvidenceResult(decision=decision, evidence_graph=evidence_graph)

    def explanation(
        self, decision_id: str, context: TenantContext | None = None
    ) -> DecisionExplanation:
        self.get(decision_id, context)
        explanation = self._decision_repository.get_explanation(decision_id)
        if explanation is None:
            raise EvidenceUnavailableError(
                f"Decision {decision_id!r} has no persisted explanation."
            )
        return explanation

    def lineage(
        self,
        decision_id: str,
        *,
        depth: int = 2,
        context: TenantContext | None = None,
    ) -> DecisionLineageResult:
        decision = self.get(decision_id, context)
        return DecisionLineageResult(
            decision=decision,
            subgraph=self._graph_query_service.get_neighbourhood(
                EntityType.GOVERNANCE_DECISION.value,
                decision_id,
                depth=depth,
                limit=100,
            ),
        )

    def _reason(
        self,
        request: GovernanceReasoningRequest,
    ) -> GovernanceReasoningOutcome:
        try:
            return self._reasoning_engine.reason(request)
        except DecisionValidationError as exc:
            raise InvalidDecisionRequestError(str(exc)) from exc
        except Exception as exc:
            raise DecisionReasoningFailedError(str(exc)) from exc

    def _enforce_evaluation_operation(
        self,
        context: TenantContext | None,
        request: GovernanceReasoningRequest,
    ) -> None:
        """Let plugins narrow high-impact decision outcomes after Core RBAC."""
        if context is None:
            return
        action = {
            DecisionType.APPROVE: "governance.decision.approve",
            DecisionType.REJECT: "governance.decision.reject",
            DecisionType.ARCHIVE: "governance.decision.archive",
        }.get(request.decision_type)
        if action is None:
            return
        enforcement_request = AuthorizationEnforcementRequest(
            context=context,
            action=action,
            resource=AuthorizationResourceFacts(
                resource_type="GovernanceDecision",
                resource_id=request.target_id,
                organization_id=context.organization_id,
                project_id=context.project_id,
                lifecycle_state="PROPOSED",
                attributes={"target_type": request.target_type.value},
            ),
        )
        for enforcer in self._authorization_enforcers:
            decision = enforcer.authorize(enforcement_request)
            if not decision.allowed:
                from ai_governance.tenancy.errors import AuthorizationDenied

                raise AuthorizationDenied(decision)

    def _existing_result(
        self,
        decision: GovernanceDecision,
        request_fingerprint: str,
    ) -> DecisionEvaluationResult:
        stored_fingerprint = decision.metadata.get(REQUEST_FINGERPRINT_METADATA_KEY)
        if stored_fingerprint is not None and stored_fingerprint != request_fingerprint:
            raise DecisionConflictError(
                "Decision idempotency key or deterministic decision ID was "
                "reused with different input."
            )

        explanation = self._decision_repository.get_explanation(decision.decision_id)
        if explanation is None:
            raise EvidenceUnavailableError(
                f"Decision {decision.decision_id!r} has no persisted explanation."
            )

        return DecisionEvaluationResult(
            decision=decision,
            explanation=explanation,
            evidence_summary=_evidence_summary_from_metadata(decision),
            policy_outcomes=_policy_outcomes_from_metadata(decision),
        )


def _request_fingerprint(request: GovernanceReasoningRequest) -> str:
    return _stable_hash(
        {
            "target_type": request.target_type.value,
            "target_id": request.target_id,
            "decision_type": request.decision_type.value,
            "policy_ids": request.policy_ids,
            "correlation_id": request.correlation_id,
            "request_id": request.request_id,
            "metadata": request.metadata,
        }
    )


def _decision_in_context(
    decision: GovernanceDecision, context: TenantContext | None
) -> bool:
    if context is None:
        return True
    return (
        decision.metadata.get("_organization_id", "org_default")
        == context.organization_id
        and decision.metadata.get("_project_id", "project_default")
        == context.project_id
    )


def _with_reasoning_metadata(
    outcome: GovernanceReasoningOutcome,
    request_fingerprint: str,
) -> GovernanceDecision:
    return replace(
        outcome.decision,
        metadata={
            **dict(outcome.decision.metadata),
            REQUEST_FINGERPRINT_METADATA_KEY: request_fingerprint,
            EVIDENCE_SUMMARY_METADATA_KEY: _evidence_summary_to_dict(
                outcome.evidence_summary
            ),
            POLICY_OUTCOMES_METADATA_KEY: [
                _policy_outcome_to_dict(outcome) for outcome in outcome.policy_outcomes
            ],
            RECORDED_AT_METADATA_KEY: datetime.now(UTC).isoformat(),
        },
    )


def _decision_recorded_at(decision: GovernanceDecision) -> datetime:
    recorded = decision.metadata.get(RECORDED_AT_METADATA_KEY)
    if isinstance(recorded, str):
        return datetime.fromisoformat(recorded)
    return decision.finalized_at or decision.provenance.created_at


def _evidence_summary_to_dict(
    summary: ReasoningEvidenceSummary,
) -> dict[str, Any]:
    return {
        "target_type": summary.target_type.value,
        "target_id": summary.target_id,
        "metric_scores": dict(summary.metric_scores),
        "metric_failures": list(summary.metric_failures),
        "threshold_breaches": list(summary.threshold_breaches),
        "drift_severity": summary.drift_severity,
        "latest_job_status": summary.latest_job_status,
        "latest_audit_status": summary.latest_audit_status,
        "evaluation_result_ids": list(summary.evaluation_result_ids),
        "metric_ids": list(summary.metric_ids),
        "drift_analysis_ids": list(summary.drift_analysis_ids),
        "leaderboard_ids": list(summary.leaderboard_ids),
        "job_ids": list(summary.job_ids),
        "mcp_audit_ids": list(summary.mcp_audit_ids),
        "policy_ids": list(summary.policy_ids),
        "missing_evidence": [
            {
                "evidence_type": item.evidence_type,
                "reason": item.reason,
                "severity": item.severity,
                "metadata": dict(item.metadata),
            }
            for item in summary.missing_evidence
        ],
        "metadata": dict(summary.metadata),
    }


def _evidence_summary_from_metadata(
    decision: GovernanceDecision,
) -> ReasoningEvidenceSummary:
    value = decision.metadata.get(EVIDENCE_SUMMARY_METADATA_KEY)
    if not isinstance(value, Mapping):
        return ReasoningEvidenceSummary(
            target_type=decision.target.target_type,
            target_id=decision.target.target_id,
        )
    return ReasoningEvidenceSummary(
        target_type=value["target_type"],
        target_id=value["target_id"],
        metric_scores=value.get("metric_scores") or {},
        metric_failures=value.get("metric_failures") or (),
        threshold_breaches=value.get("threshold_breaches") or (),
        drift_severity=value.get("drift_severity"),
        latest_job_status=value.get("latest_job_status"),
        latest_audit_status=value.get("latest_audit_status"),
        evaluation_result_ids=value.get("evaluation_result_ids") or (),
        metric_ids=value.get("metric_ids") or (),
        drift_analysis_ids=value.get("drift_analysis_ids") or (),
        leaderboard_ids=value.get("leaderboard_ids") or (),
        job_ids=value.get("job_ids") or (),
        mcp_audit_ids=value.get("mcp_audit_ids") or (),
        policy_ids=value.get("policy_ids") or (),
        missing_evidence=tuple(
            MissingEvidence(
                evidence_type=item["evidence_type"],
                reason=item["reason"],
                severity=item["severity"],
                metadata=item.get("metadata") or {},
            )
            for item in value.get("missing_evidence") or ()
            if isinstance(item, Mapping)
        ),
        metadata=value.get("metadata") or {},
    )


def _policy_outcome_to_dict(
    outcome: PolicyEvaluationOutcome,
) -> dict[str, Any]:
    return {
        "policy_id": outcome.policy_id,
        "policy_version": outcome.policy_version,
        "matched_rule_id": outcome.matched_rule_id,
        "effect": outcome.effect.value,
        "reason": outcome.reason,
        "matched": outcome.matched,
        "metadata": dict(outcome.metadata),
    }


def _policy_outcomes_from_metadata(
    decision: GovernanceDecision,
) -> tuple[PolicyEvaluationOutcome, ...]:
    values = decision.metadata.get(POLICY_OUTCOMES_METADATA_KEY)
    if not isinstance(values, Sequence) or isinstance(values, str):
        return ()
    outcomes = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        outcomes.append(
            PolicyEvaluationOutcome(
                policy_id=value["policy_id"],
                policy_version=value["policy_version"],
                matched_rule_id=value.get("matched_rule_id"),
                effect=PolicyEffect(value["effect"]),
                reason=value["reason"],
                matched=bool(value["matched"]),
                metadata=value.get("metadata") or {},
            )
        )
    return tuple(outcomes)


def public_decision_metadata(
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        key: value for key, value in metadata.items() if not str(key).startswith("_")
    }


def _stable_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
