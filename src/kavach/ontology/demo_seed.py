from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from kavach.decisions import (
    DecisionEvidenceBuilder,
    DecisionTargetType,
    GovernancePolicy,
    GovernancePolicyEvaluator,
    GovernanceReasoningEngine,
    InMemoryGovernancePolicyProvider,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyRule,
    PolicyStatus,
    ReasoningEvidenceSummarizer,
)
from kavach.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from kavach.decisions.policy_enums import PolicyCategory
from kavach.domain.jobs import Job, JobStatus, JobType, WorkerHeartbeat
from kavach.mcp.audit import (
    MCPExecutionAuditLog,
    MCPExecutionAuditRecord,
    request_hash,
    safe_summary,
)
from kavach.ontology.enums import EntityType, RelationshipType
from kavach.ontology.repositories import OntologyGraphRepository
from kavach.ontology.service import OntologyService
from kavach.repositories.governance_decision_repository import (
    GovernanceDecisionRepository,
)
from kavach.repositories.job_repository import JobRepository
from kavach.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)
from kavach.services.decision_application_service import (
    DecisionEvaluateCommand,
    GovernanceDecisionApplicationService,
)
from kavach.services.job_submission_service import stable_input_hash
from kavach.version import __version__

DEMO_ENTITY_TYPE = EntityType.CANDIDATE.value
DEMO_ENTITY_ID = "candidate-1"
DEMO_DECISION_POLICY_ID = "policy-release-gate"
# Bump the seed namespace when the decision input contract changes. This keeps
# existing local databases from treating updated demo data as an idempotency
# conflict during application startup.
DEMO_DECISION_REQUEST_ID = "demo-decision-seed-approve-v2"

_CREATED_AT = datetime(2026, 7, 1, tzinfo=UTC)


@dataclass(frozen=True)
class DemoDecisionScenario:
    suffix: str
    candidate_id: str
    label: str
    score: float
    decision_type: str
    request_id: str


DEMO_DECISION_SCENARIOS = (
    DemoDecisionScenario(
        suffix="approve",
        candidate_id=DEMO_ENTITY_ID,
        label="Candidate A",
        score=0.91,
        decision_type="APPROVE",
        request_id=DEMO_DECISION_REQUEST_ID,
    ),
    DemoDecisionScenario(
        suffix="review",
        candidate_id="candidate-2",
        label="Candidate B",
        score=0.84,
        decision_type="INVESTIGATE",
        request_id="demo-decision-seed-review-v2",
    ),
    DemoDecisionScenario(
        suffix="reject",
        candidate_id="candidate-3",
        label="Candidate C",
        score=0.68,
        decision_type="REJECT",
        request_id="demo-decision-seed-reject-v2",
    ),
    DemoDecisionScenario(
        suffix="block",
        candidate_id="candidate-4",
        label="Candidate D",
        score=0.43,
        decision_type="BLOCK",
        request_id="demo-decision-seed-block-v2",
    ),
)


def seed_demo_ontology_graph(repository: OntologyGraphRepository) -> None:
    """
    Seed a small ontology graph for local console visualization.

    The seed uses stable IDs and valid ontology relationships so repeated calls
    update the same in-memory graph instead of creating duplicate demo data.
    """

    service = OntologyService(repository)
    for entity in _demo_entities():
        service.create_entity(**entity)
    for relationship in _demo_relationships():
        service.create_relationship(**relationship)


def demo_governance_decision_service(
    *,
    decision_repository: GovernanceDecisionRepository,
    graph_query_service: Any,
) -> GovernanceDecisionApplicationService:
    """
    Build a demo-only decision service with a release gate policy.
    """

    evidence_builder = DecisionEvidenceBuilder(graph_query_service)
    return GovernanceDecisionApplicationService(
        reasoning_engine=GovernanceReasoningEngine(
            evidence_builder=evidence_builder,
            evidence_summarizer=ReasoningEvidenceSummarizer(),
            policy_evaluator=GovernancePolicyEvaluator(),
            policy_provider=InMemoryGovernancePolicyProvider(
                (_demo_release_gate_policy(),)
            ),
        ),
        decision_repository=decision_repository,
        evidence_builder=evidence_builder,
        graph_query_service=graph_query_service,
    )


def seed_demo_ontology_graph_decision(
    repository: OntologyGraphRepository,
    decision_service: GovernanceDecisionApplicationService,
    *,
    organization_id: str = "org_default",
    project_id: str = "project_default",
) -> tuple[str, ...]:
    """
    Evaluate and project stable demo governance decisions for the console.
    """

    service = OntologyService(repository)
    decision_ids: list[str] = []
    for scenario in DEMO_DECISION_SCENARIOS:
        result = decision_service.evaluate(
            DecisionEvaluateCommand(
                target_type=DecisionTargetType.CANDIDATE,
                target_id=scenario.candidate_id,
                decision_type=scenario.decision_type,
                policy_ids=(DEMO_DECISION_POLICY_ID,),
                correlation_id="demo-governance-console",
                request_id=scenario.request_id,
                metadata={
                    "source": "demo-seed",
                    "demo": True,
                    "scenario": scenario.suffix,
                    "_organization_id": organization_id,
                    "_project_id": project_id,
                },
            )
        )
        decision = result.decision
        decision_ids.append(decision.decision_id)

        service.create_entity(
            **_entity(
                EntityType.GOVERNANCE_DECISION.value,
                decision.decision_id,
                owner="owner",
                lifecycle=decision.status.value.lower(),
                label=f"{decision.status.value.title()} {scenario.label}",
            )
        )
        service.create_relationship(
            **_relationship(
                f"demo-rel-decision-target-{decision.decision_id}",
                EntityType.GOVERNANCE_DECISION.value,
                decision.decision_id,
                RelationshipType.DECIDES_ON.value,
                EntityType.CANDIDATE.value,
                scenario.candidate_id,
            )
        )
        service.create_relationship(
            **_relationship(
                f"demo-rel-decision-created-{decision.decision_id}",
                EntityType.GOVERNANCE_DECISION.value,
                decision.decision_id,
                RelationshipType.CREATED_BY.value,
                EntityType.ACTOR.value,
                "owner",
            )
        )
        _create_outcome_relationship(service, decision.decision_id, scenario)

    return tuple(decision_ids)


def seed_demo_policy_administration(
    repository: PolicyAdministrationRepository,
    *,
    organization_id: str = "org_default",
    project_id: str = "project_default",
) -> str:
    """
    Seed the release-gate policy into Studio policy administration.
    """

    policy = _demo_release_gate_policy()
    definition = PolicyDefinition(
        policy_id=policy.policy_id,
        organization_id=organization_id,
        project_id=project_id,
        name=policy.name,
        description=policy.description,
        category=PolicyCategory.MODEL_RISK,
        owner="platform-governance",
        created_by=policy.created_by,
        created_at=policy.created_at,
        updated_at=policy.created_at,
        metadata={
            **policy.metadata,
            "source": "demo-seed",
            "ontology_entity_id": policy.policy_id,
        },
    )
    version = PolicyVersion(
        policy_id=policy.policy_id,
        version=policy.version,
        status=PolicyStatus.ACTIVE,
        target_types=policy.target_types,
        rules=policy.rules,
        created_by=policy.created_by,
        created_at=policy.created_at,
        activated_at=policy.created_at,
        metadata={
            **policy.metadata,
            "source": "demo-seed",
        },
    )

    repository.save_definition(definition)
    repository.save_version(version)
    return policy.policy_id


def seed_demo_jobs(repository: JobRepository) -> tuple[str, ...]:
    """
    Seed varied job execution records for the Studio Jobs page.
    """

    # Completed jobs are subject to the runtime retention policy.  Keep local
    # demo fixtures recent so the seeded inventory remains visible regardless
    # of when a developer starts the stack.
    base_time = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=12)
    job_ids: list[str] = []
    for spec in _demo_job_specs():
        created_at = base_time + timedelta(hours=spec["created_hours"])
        started_at = (
            base_time + timedelta(hours=spec["started_hours"])
            if spec.get("started_hours") is not None
            else None
        )
        completed_at = (
            base_time + timedelta(hours=spec["completed_hours"])
            if spec.get("completed_hours") is not None
            else None
        )
        heartbeat_at = (
            base_time + timedelta(hours=spec["heartbeat_hours"])
            if spec.get("heartbeat_hours") is not None
            else None
        )
        lease_expires_at = (
            base_time + timedelta(hours=spec["lease_expires_hours"])
            if spec.get("lease_expires_hours") is not None
            else None
        )
        updated_at = completed_at or heartbeat_at or started_at or created_at
        input_refs = dict(spec["input_refs"])
        job = Job(
            job_id=str(spec["job_id"]),
            job_type=spec["job_type"],
            status=spec["status"],
            input_refs=input_refs,
            input_hash=stable_input_hash(input_refs),
            idempotency_key=str(spec["idempotency_key"]),
            submitted_by=str(spec["submitted_by"]),
            attempt_count=int(spec["attempt_count"]),
            max_attempts=int(spec["max_attempts"]),
            result_ref=spec.get("result_ref"),
            failure_reason=spec.get("failure_reason"),
            leased_by=spec.get("leased_by"),
            lease_expires_at=lease_expires_at,
            heartbeat_at=heartbeat_at,
            created_at=created_at,
            updated_at=updated_at,
            started_at=started_at,
            completed_at=completed_at,
        )
        repository.save(job)
        job_ids.append(job.job_id)

    return tuple(job_ids)


def seed_demo_workers(repository: JobRepository) -> tuple[str, ...]:
    """Register representative workers for local and Docker dashboard demos."""
    heartbeat_at = datetime.now(UTC)
    workers = (
        WorkerHeartbeat("worker-local-1", "demo", heartbeat_at),
        WorkerHeartbeat("worker-local-2", "demo", heartbeat_at),
    )
    for worker in workers:
        repository.register_worker(worker)
    return tuple(worker.worker_id for worker in workers)


def seed_demo_mcp_audit_log(
    audit_log: MCPExecutionAuditLog,
) -> tuple[str, ...]:
    """
    Seed varied MCP execution audit rows for the Studio Audit page.
    """

    audit_ids: list[str] = []
    for spec in _demo_audit_specs():
        payload = dict(spec["payload"])
        started_at = _CREATED_AT + timedelta(hours=spec["started_hours"])
        completed_at = (
            _CREATED_AT + timedelta(hours=spec["completed_hours"])
            if spec.get("completed_hours") is not None
            else None
        )
        duration_ms = (
            (completed_at - started_at).total_seconds() * 1000
            if completed_at is not None
            else None
        )
        record = MCPExecutionAuditRecord(
            audit_id=str(spec["audit_id"]),
            request_id=str(spec["request_id"]),
            correlation_id=str(spec["correlation_id"]),
            tool_name=str(spec["tool_name"]),
            tool_version=__version__,
            actor_id=str(spec["actor_id"]),
            actor_type=str(spec["actor_type"]),
            agent_name=spec.get("agent_name"),
            agent_session_id=spec.get("agent_session_id"),
            client_name=spec.get("client_name"),
            client_version=spec.get("client_version"),
            idempotency_key=str(spec["idempotency_key"]),
            operation_type=str(spec["operation_type"]),
            resource_type=str(spec["resource_type"]),
            resource_id=spec.get("resource_id"),
            request_hash=request_hash(payload),
            request_summary=safe_summary(payload),
            resolved_versions=dict(spec["resolved_versions"]),
            reason=str(spec["reason"]),
            dry_run=bool(spec["dry_run"]),
            status=str(spec["status"]),
            job_id=spec.get("job_id"),
            result_reference=spec.get("result_reference"),
            error_code=spec.get("error_code"),
            error_message=spec.get("error_message"),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            metadata=dict(spec["metadata"]),
        )
        audit_log.save_record(record)
        audit_ids.append(record.audit_id)

    return tuple(audit_ids)


def _demo_job_specs() -> tuple[dict[str, Any], ...]:
    return (
        _job_spec(
            "job-demo-eval-approve",
            JobType.EVALUATION,
            JobStatus.SUCCEEDED,
            {"candidate_id": "candidate-1", "evaluation_run": "eval-run-approve"},
            result_ref="evaluation-result:eval-result-approve",
            created_hours=2,
            started_hours=2.1,
            completed_hours=2.4,
        ),
        _job_spec(
            "job-demo-eval-review",
            JobType.EVALUATION,
            JobStatus.SUCCEEDED,
            {"candidate_id": "candidate-2", "evaluation_run": "eval-run-review"},
            result_ref="evaluation-result:eval-result-review",
            created_hours=3,
            started_hours=3.1,
            completed_hours=3.45,
        ),
        _job_spec(
            "job-demo-eval-reject",
            JobType.EVALUATION,
            JobStatus.FAILED,
            {"candidate_id": "candidate-3", "evaluation_run": "eval-run-reject"},
            attempt_count=2,
            failure_reason="Answer relevance score remained below release gate.",
            created_hours=4,
            started_hours=4.1,
            completed_hours=4.5,
        ),
        _job_spec(
            "job-demo-eval-block",
            JobType.EVALUATION,
            JobStatus.SUCCEEDED,
            {"candidate_id": "candidate-4", "evaluation_run": "eval-run-block"},
            result_ref="evaluation-result:eval-result-block",
            created_hours=5,
            started_hours=5.1,
            completed_hours=5.25,
        ),
        _job_spec(
            "job-demo-experiment-baseline",
            JobType.EXPERIMENT,
            JobStatus.SUCCEEDED,
            {"experiment_id": "experiment-1", "policy_id": DEMO_DECISION_POLICY_ID},
            result_ref="leaderboard:insurance-platform-baseline",
            created_hours=6,
            started_hours=6.1,
            completed_hours=6.9,
            submitted_by="platform-governance",
        ),
        _job_spec(
            "job-demo-experiment-candidate-sweep",
            JobType.EXPERIMENT,
            JobStatus.SUCCEEDED,
            {"experiment_id": "experiment-1", "candidate_batch": "release-cohort"},
            result_ref="leaderboard:insurance-platform-candidate-sweep",
            created_hours=7,
            started_hours=7.1,
            completed_hours=7.8,
            submitted_by="platform-governance",
        ),
        _job_spec(
            "job-demo-replay-release-gate",
            JobType.REPLAY,
            JobStatus.SUCCEEDED,
            {"policy_id": DEMO_DECISION_POLICY_ID, "window": "last-7-days"},
            result_ref="replay-result:release-gate-last-7-days",
            created_hours=8,
            started_hours=8.1,
            completed_hours=8.7,
        ),
        _job_spec(
            "job-demo-replay-cancelled",
            JobType.REPLAY,
            JobStatus.CANCELLED,
            {"policy_id": DEMO_DECISION_POLICY_ID, "window": "last-30-days"},
            created_hours=9,
            started_hours=9.1,
            completed_hours=9.2,
            submitted_by="studio-admin",
        ),
        _job_spec(
            "job-demo-drift-nightly",
            JobType.DRIFT_ANALYSIS,
            JobStatus.SUCCEEDED,
            {"dataset_id": "dataset-v1", "metric": "answer_relevance"},
            result_ref="drift-analysis:dataset-v1:answer-relevance",
            created_hours=10,
            started_hours=10.1,
            completed_hours=10.6,
            submitted_by="platform-governance",
        ),
        _job_spec(
            "job-demo-drift-threshold",
            JobType.DRIFT_ANALYSIS,
            JobStatus.FAILED,
            {"dataset_id": "dataset-v1", "metric": "answer_relevance"},
            attempt_count=3,
            failure_reason="Drift analysis exceeded the configured retry budget.",
            created_hours=11,
            started_hours=11.1,
            completed_hours=11.6,
            submitted_by="platform-governance",
        ),
    )


def _demo_audit_specs() -> tuple[dict[str, Any], ...]:
    return (
        _audit_spec(
            "audit-demo-evaluation-submit-approve",
            request_id="request-demo-eval-approve",
            correlation_id="corr-demo-release-gate",
            tool_name="evaluation.submit_async",
            operation_type="SUBMIT_EVALUATION_JOB",
            resource_type="evaluation",
            resource_id="execution-approve",
            actor_id="platform-governance",
            status="SUCCEEDED",
            job_id="job-demo-eval-approve",
            started_hours=12.0,
            completed_hours=12.03,
            payload={
                "execution_id": "execution-approve",
                "provider_config": {"api_key": "secret"},
            },
            resolved_versions={"provider_name": "mock-provider"},
        ),
        _audit_spec(
            "audit-demo-experiment-create",
            request_id="request-demo-experiment-create",
            correlation_id="corr-demo-experiment-1",
            tool_name="experiment.create",
            operation_type="CREATE_EXPERIMENT",
            resource_type="experiment",
            resource_id="experiment-1",
            actor_id="studio-admin",
            status="SUCCEEDED",
            job_id="job-demo-experiment-baseline",
            started_hours=12.2,
            completed_hours=12.24,
            payload={
                "name": "Support Bot Prompt Trial",
                "request_id": "request-demo-experiment-create",
            },
        ),
        _audit_spec(
            "audit-demo-experiment-run-dry-run",
            request_id="request-demo-experiment-run",
            correlation_id="corr-demo-experiment-1",
            tool_name="experiment.run_async",
            operation_type="RUN_EXPERIMENT",
            resource_type="experiment",
            resource_id="experiment-1",
            actor_id="studio-admin",
            status="DRY_RUN",
            dry_run=True,
            started_hours=12.5,
            completed_hours=12.51,
            payload={
                "experiment_id": "experiment-1",
                "provider_config": {"api_key": "secret"},
            },
        ),
        _audit_spec(
            "audit-demo-job-retry-started",
            request_id="request-demo-job-retry-started",
            correlation_id="corr-demo-drift-retry",
            tool_name="job.retry",
            operation_type="RETRY_JOB",
            resource_type="job",
            resource_id="job-demo-drift-threshold",
            actor_id="platform-governance",
            status="STARTED",
            started_hours=12.8,
            payload={"job_id": "job-demo-drift-threshold"},
        ),
        _audit_spec(
            "audit-demo-job-retry-succeeded",
            request_id="request-demo-job-retry-succeeded",
            correlation_id="corr-demo-drift-retry",
            tool_name="job.retry",
            operation_type="RETRY_JOB",
            resource_type="job",
            resource_id="job-demo-drift-threshold",
            actor_id="platform-governance",
            status="SUCCEEDED",
            job_id="job-demo-drift-threshold",
            started_hours=13.0,
            completed_hours=13.02,
            payload={"job_id": "job-demo-drift-threshold"},
        ),
        _audit_spec(
            "audit-demo-evaluation-submit-failed",
            request_id="request-demo-eval-failed",
            correlation_id="corr-demo-eval-failed",
            tool_name="evaluation.submit_async",
            operation_type="SUBMIT_EVALUATION_JOB",
            resource_type="evaluation",
            resource_id="execution-reject",
            actor_id="platform-governance",
            status="FAILED",
            error_code="PROVIDER_NOT_FOUND",
            error_message="Provider 'mock-provider' was not available.",
            started_hours=13.3,
            completed_hours=13.34,
            payload={
                "execution_id": "execution-reject",
                "provider_name": "mock-provider",
            },
        ),
        _audit_spec(
            "audit-demo-job-cancel-succeeded",
            request_id="request-demo-job-cancel",
            correlation_id="corr-demo-replay-cancel",
            tool_name="job.cancel",
            operation_type="CANCEL_JOB",
            resource_type="job",
            resource_id="job-demo-replay-cancelled",
            actor_id="studio-admin",
            status="SUCCEEDED",
            job_id="job-demo-replay-cancelled",
            started_hours=13.6,
            completed_hours=13.62,
            payload={"job_id": "job-demo-replay-cancelled"},
        ),
        _audit_spec(
            "audit-demo-experiment-add-candidate",
            request_id="request-demo-experiment-candidate",
            correlation_id="corr-demo-experiment-candidate",
            tool_name="experiment.add_candidate",
            operation_type="ADD_EXPERIMENT_CANDIDATE",
            resource_type="experiment_candidate",
            resource_id="experiment-1",
            actor_id="platform-governance",
            status="SUCCEEDED",
            job_id="job-demo-experiment-candidate-sweep",
            started_hours=13.8,
            completed_hours=13.83,
            payload={
                "experiment_id": "experiment-1",
                "candidate_name": "Candidate E",
            },
            resolved_versions={
                "prompt_version": "prompt-v1",
                "model_version": "model-v1",
                "dataset_version": "dataset-v1",
            },
        ),
    )


def _job_spec(
    job_id: str,
    job_type: JobType,
    status: JobStatus,
    input_refs: dict[str, Any],
    *,
    result_ref: str | None = None,
    failure_reason: str | None = None,
    attempt_count: int = 0,
    max_attempts: int = 3,
    leased_by: str | None = None,
    created_hours: float,
    started_hours: float | None = None,
    completed_hours: float | None = None,
    heartbeat_hours: float | None = None,
    lease_expires_hours: float | None = None,
    submitted_by: str = "demo-seed",
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "input_refs": input_refs,
        "result_ref": result_ref,
        "failure_reason": failure_reason,
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "leased_by": leased_by,
        "created_hours": created_hours,
        "started_hours": started_hours,
        "completed_hours": completed_hours,
        "heartbeat_hours": heartbeat_hours,
        "lease_expires_hours": lease_expires_hours,
        "submitted_by": submitted_by,
        "idempotency_key": f"demo-seed:{job_id}",
    }


def _audit_spec(
    audit_id: str,
    *,
    request_id: str,
    correlation_id: str,
    tool_name: str,
    operation_type: str,
    resource_type: str,
    resource_id: str | None,
    actor_id: str,
    status: str,
    started_hours: float,
    payload: dict[str, Any],
    completed_hours: float | None = None,
    dry_run: bool = False,
    job_id: str | None = None,
    result_reference: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    resolved_versions: dict[str, Any] | None = None,
    reason: str = "demo seed audit record",
    actor_type: str = "AGENT",
    agent_name: str | None = "demo-seed",
    agent_session_id: str | None = "demo-seed-session",
    client_name: str | None = "Kavach Studio",
    client_version: str | None = "0.1.3",
) -> dict[str, Any]:
    return {
        "audit_id": audit_id,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "tool_name": tool_name,
        "actor_id": actor_id,
        "actor_type": actor_type,
        "agent_name": agent_name,
        "agent_session_id": agent_session_id,
        "client_name": client_name,
        "client_version": client_version,
        "idempotency_key": f"demo-seed:{audit_id}",
        "operation_type": operation_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "reason": reason,
        "dry_run": dry_run,
        "status": status,
        "job_id": job_id,
        "result_reference": result_reference,
        "error_code": error_code,
        "error_message": error_message,
        "started_hours": started_hours,
        "completed_hours": completed_hours,
        "payload": payload,
        "resolved_versions": resolved_versions or {},
        "metadata": {
            "demo": True,
            "source": "demo-seed",
        },
    }


def _create_outcome_relationship(
    service: OntologyService,
    decision_id: str,
    scenario: DemoDecisionScenario,
) -> None:
    if scenario.decision_type == "APPROVE":
        service.create_relationship(
            **_relationship(
                f"demo-rel-decision-approved-{decision_id}",
                EntityType.GOVERNANCE_DECISION.value,
                decision_id,
                RelationshipType.APPROVED_BY.value,
                EntityType.ACTOR.value,
                "owner",
            )
        )
    elif scenario.decision_type == "REJECT":
        service.create_relationship(
            **_relationship(
                f"demo-rel-decision-rejected-{decision_id}",
                EntityType.GOVERNANCE_DECISION.value,
                decision_id,
                RelationshipType.REJECTED_BY.value,
                EntityType.ACTOR.value,
                "owner",
            )
        )
    elif scenario.decision_type == "BLOCK":
        service.create_relationship(
            **_relationship(
                f"demo-rel-decision-blocked-{decision_id}",
                EntityType.GOVERNANCE_DECISION.value,
                decision_id,
                RelationshipType.BLOCKED_BY.value,
                EntityType.POLICY.value,
                DEMO_DECISION_POLICY_ID,
            )
        )


def _demo_entities() -> tuple[dict[str, object], ...]:
    shared_entities = (
        _entity(
            EntityType.ACTOR.value,
            "owner",
            owner="platform-governance",
            lifecycle="active",
            label="Platform Governance",
        ),
        _entity(
            EntityType.EXPERIMENT.value,
            "experiment-1",
            owner="owner",
            lifecycle="running",
            label="Support Bot Prompt Trial",
        ),
        _entity(
            EntityType.PROMPT_VERSION.value,
            "prompt-v1",
            owner="owner",
            lifecycle="active",
            label="Support Prompt v1",
        ),
        _entity(
            EntityType.MODEL_VERSION.value,
            "model-v1",
            owner="owner",
            lifecycle="active",
            label="gpt-4.1-mini",
        ),
        _entity(
            EntityType.DATASET_VERSION.value,
            "dataset-v1",
            owner="owner",
            lifecycle="active",
            label="Support Eval Dataset v1",
        ),
        _entity(
            EntityType.EVALUATION_PROVIDER.value,
            "mock-provider",
            owner="owner",
            lifecycle="active",
            label="Mock Evaluator",
        ),
        _entity(
            EntityType.POLICY.value,
            "policy-release-gate",
            owner="owner",
            lifecycle="active",
            label="Release Gate Policy",
        ),
    )
    return shared_entities + tuple(
        entity
        for scenario in DEMO_DECISION_SCENARIOS
        for entity in _scenario_entities(scenario)
    )


def _scenario_entities(
    scenario: DemoDecisionScenario,
) -> tuple[dict[str, object], ...]:
    return (
        _entity(
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
            owner="owner",
            lifecycle="active",
            label=scenario.label,
            score=scenario.score,
        ),
        _entity(
            EntityType.EVALUATION_RUN.value,
            f"eval-run-{scenario.suffix}",
            owner="owner",
            lifecycle="completed",
            label=f"{scenario.label} Evaluation",
        ),
        _entity(
            EntityType.EVALUATION_RESULT.value,
            f"eval-result-{scenario.suffix}",
            owner="owner",
            lifecycle="completed",
            label=f"{scenario.label} Result",
            score=scenario.score,
        ),
        _entity(
            EntityType.METRIC.value,
            f"answer-relevance-{scenario.suffix}",
            owner="owner",
            lifecycle="active",
            label="Answer Relevance",
            score=scenario.score,
        ),
        _entity(
            EntityType.JOB.value,
            f"job-eval-{scenario.suffix}",
            owner="owner",
            lifecycle="completed",
            label=f"{scenario.label} Evaluation Job",
            status=_job_status_for(scenario),
        ),
    )


def _demo_relationships() -> tuple[dict[str, object], ...]:
    return tuple(
        relationship
        for scenario in DEMO_DECISION_SCENARIOS
        for relationship in _scenario_relationships(scenario)
    )


def _scenario_relationships(
    scenario: DemoDecisionScenario,
) -> tuple[dict[str, object], ...]:
    suffix = scenario.suffix
    return (
        _relationship(
            f"demo-rel-{suffix}-candidate",
            EntityType.EXPERIMENT.value,
            "experiment-1",
            RelationshipType.HAS_CANDIDATE.value,
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
        ),
        _relationship(
            f"demo-rel-{suffix}-prompt",
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
            RelationshipType.USES.value,
            EntityType.PROMPT_VERSION.value,
            "prompt-v1",
        ),
        _relationship(
            f"demo-rel-{suffix}-model",
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
            RelationshipType.USES.value,
            EntityType.MODEL_VERSION.value,
            "model-v1",
        ),
        _relationship(
            f"demo-rel-{suffix}-dataset",
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
            RelationshipType.USES.value,
            EntityType.DATASET_VERSION.value,
            "dataset-v1",
        ),
        _relationship(
            f"demo-rel-{suffix}-provider",
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
            RelationshipType.EVALUATED_BY.value,
            EntityType.EVALUATION_PROVIDER.value,
            "mock-provider",
        ),
        _relationship(
            f"demo-rel-{suffix}-run",
            EntityType.EXPERIMENT.value,
            "experiment-1",
            RelationshipType.HAS_RUN.value,
            EntityType.EVALUATION_RUN.value,
            f"eval-run-{suffix}",
        ),
        _relationship(
            f"demo-rel-{suffix}-executes",
            EntityType.EVALUATION_RUN.value,
            f"eval-run-{suffix}",
            RelationshipType.EXECUTES.value,
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
        ),
        _relationship(
            f"demo-rel-{suffix}-result",
            EntityType.EVALUATION_RUN.value,
            f"eval-run-{suffix}",
            RelationshipType.PRODUCES.value,
            EntityType.EVALUATION_RESULT.value,
            f"eval-result-{suffix}",
        ),
        _relationship(
            f"demo-rel-{suffix}-metric",
            EntityType.EVALUATION_RESULT.value,
            f"eval-result-{suffix}",
            RelationshipType.HAS_METRIC.value,
            EntityType.METRIC.value,
            f"answer-relevance-{suffix}",
        ),
        _relationship(
            f"demo-rel-{suffix}-owner",
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
            RelationshipType.OWNED_BY.value,
            EntityType.ACTOR.value,
            "owner",
        ),
        _relationship(
            f"demo-rel-{suffix}-policy",
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
            RelationshipType.GOVERNED_BY.value,
            EntityType.POLICY.value,
            DEMO_DECISION_POLICY_ID,
        ),
        _relationship(
            f"demo-rel-{suffix}-job",
            EntityType.CANDIDATE.value,
            scenario.candidate_id,
            RelationshipType.SUBMITTED_AS.value,
            EntityType.JOB.value,
            f"job-eval-{suffix}",
        ),
        _relationship(
            f"demo-rel-{suffix}-job-result",
            EntityType.JOB.value,
            f"job-eval-{suffix}",
            RelationshipType.RESULTED_IN.value,
            EntityType.EVALUATION_RESULT.value,
            f"eval-result-{suffix}",
        ),
    )


def _demo_release_gate_policy() -> GovernancePolicy:
    return GovernancePolicy(
        policy_id=DEMO_DECISION_POLICY_ID,
        version="1",
        name="Release Gate Policy",
        description="Route demo candidates by answer relevance score bands.",
        status=PolicyStatus.ACTIVE,
        target_types=(DecisionTargetType.CANDIDATE,),
        rules=(
            PolicyRule(
                rule_id="answer-relevance-lt-0.5",
                name="Block very low answer relevance",
                conditions=(
                    PolicyCondition(
                        field_path="metrics.answer_relevance.score",
                        operator=PolicyConditionOperator.LESS_THAN,
                        expected_value=0.5,
                    ),
                ),
                effect=PolicyEffect.BLOCK,
                reason_template=(
                    "Candidate was blocked because answer relevance is below 0.50."
                ),
                priority=1,
            ),
            PolicyRule(
                rule_id="answer-relevance-lt-0.75",
                name="Reject low answer relevance",
                conditions=(
                    PolicyCondition(
                        field_path="metrics.answer_relevance.score",
                        operator=PolicyConditionOperator.LESS_THAN,
                        expected_value=0.75,
                    ),
                ),
                effect=PolicyEffect.REJECT,
                reason_template=(
                    "Candidate was rejected because answer relevance is below 0.75."
                ),
                priority=2,
            ),
            PolicyRule(
                rule_id="answer-relevance-lt-0.9",
                name="Investigate borderline answer relevance",
                conditions=(
                    PolicyCondition(
                        field_path="metrics.answer_relevance.score",
                        operator=PolicyConditionOperator.LESS_THAN,
                        expected_value=0.9,
                    ),
                ),
                effect=PolicyEffect.INVESTIGATE,
                reason_template=(
                    "Candidate needs review because answer relevance is below 0.90."
                ),
                priority=3,
            ),
            PolicyRule(
                rule_id="answer-relevance-gte-0.9",
                name="Answer relevance gate",
                conditions=(
                    PolicyCondition(
                        field_path="metrics.answer_relevance.score",
                        operator=PolicyConditionOperator.GREATER_THAN_OR_EQUAL,
                        expected_value=0.9,
                    ),
                ),
                effect=PolicyEffect.APPROVE,
                reason_template=(
                    "Candidate passed the release gate with answer relevance "
                    "at or above 0.90."
                ),
                priority=4,
            ),
        ),
        created_by="demo-seed",
        created_at=_CREATED_AT,
        metadata={"demo": True},
    )


def _job_status_for(scenario: DemoDecisionScenario) -> str:
    if scenario.decision_type == "APPROVE":
        return "SUCCEEDED"
    if scenario.decision_type == "INVESTIGATE":
        return "REVIEW"
    if scenario.decision_type == "REJECT":
        return "FAILED"
    return "BLOCKED"


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    owner: str,
    lifecycle: str,
    label: str,
    score: float | None = None,
    status: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {"label": label, "demo": True}
    if score is not None:
        metadata["score"] = score
    if status is not None:
        metadata["status"] = status
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "owner": owner,
        "lifecycle": lifecycle,
        "created_at": _CREATED_AT,
        "immutable_attributes": {"demo_id": entity_id},
        "mutable_attributes": {},
        "metadata": metadata,
    }


def _relationship(
    relationship_id: str,
    source_type: str,
    source_id: str,
    relationship_type: str,
    target_type: str,
    target_id: str,
) -> dict[str, object]:
    return {
        "relationship_id": relationship_id,
        "source_type": source_type,
        "source_id": source_id,
        "relationship_type": relationship_type,
        "target_type": target_type,
        "target_id": target_id,
        "created_by": "demo-seed",
        "created_at": _CREATED_AT,
        "metadata": {"demo": True},
    }
