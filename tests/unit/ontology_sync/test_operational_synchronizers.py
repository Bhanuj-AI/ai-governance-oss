from datetime import UTC, datetime

from kavach.domain.history import EvaluationHistory, EvaluationHistoryRecord
from kavach.domain.jobs import Job, JobStatus, JobType
from kavach.domain.replay import ReplayEvaluationHistory, ReplayRequest
from kavach.domain.workflow_execution import WorkflowExecution
from kavach.mcp.audit import MCPExecutionAuditRecord
from kavach.ontology import (
    EntityType,
    InMemoryOntologyGraphRepository,
    OntologyService,
    RelationshipType,
)
from kavach.ontology.synchronization import (
    JobOntologySynchronizer,
    MCPAuditOntologySynchronizer,
    ReplayOntologySynchronizer,
    WorkflowExecutionOntologySynchronizer,
)


def test_job_synchronization_links_result_reference_when_available() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    service.create_entity(
        entity_id="eval-1",
        entity_type=EntityType.EVALUATION_RESULT,
        owner="mock",
        lifecycle="COMPLETED",
    )
    now = datetime(2026, 6, 30, tzinfo=UTC)
    job = Job(
        job_id="job-1",
        job_type=JobType.EVALUATION,
        status=JobStatus.SUCCEEDED,
        input_refs={},
        input_hash="hash",
        idempotency_key="key",
        submitted_by="operator",
        attempt_count=1,
        max_attempts=3,
        result_ref="evaluation:eval-1",
        failure_reason=None,
        leased_by=None,
        lease_expires_at=None,
        heartbeat_at=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
    )

    result = JobOntologySynchronizer(service).synchronize(job)

    assert result.succeeded is True
    assert service.find_relationships(
        "Job",
        "job-1",
        direction="outgoing",
        relationship_type=RelationshipType.RESULTED_IN.value,
    )


def test_mcp_audit_synchronization_references_resource() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    service.create_entity(
        entity_id="job-1",
        entity_type=EntityType.JOB,
        owner="operator",
        lifecycle="SUCCEEDED",
    )
    record = MCPExecutionAuditRecord(
        audit_id="audit-1",
        request_id="request-1",
        correlation_id="correlation-1",
        tool_name="jobs.cancel",
        tool_version="1.1.1",
        actor_id="operator",
        actor_type="user",
        agent_name=None,
        agent_session_id=None,
        client_name=None,
        client_version=None,
        idempotency_key="key",
        operation_type="CANCEL_JOB",
        resource_type="job",
        resource_id="job-1",
        request_hash="hash",
        request_summary={},
        resolved_versions={},
        reason="test",
        dry_run=False,
        status="SUCCEEDED",
        job_id="job-1",
        result_reference=None,
        error_code=None,
        error_message=None,
        started_at=datetime(2026, 6, 30, tzinfo=UTC),
        completed_at=datetime(2026, 6, 30, tzinfo=UTC),
        duration_ms=1.0,
    )

    result = MCPAuditOntologySynchronizer(service).synchronize(record)

    assert result.succeeded is True
    assert service.find_relationships(
        "MCPAuditRecord",
        "audit-1",
        direction="outgoing",
        relationship_type=RelationshipType.REFERENCES_RESOURCE.value,
    )


def test_replay_synchronization_links_workflow_and_evaluations() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    service.create_entity(
        entity_id="eval-1",
        entity_type=EntityType.EVALUATION_RESULT,
        owner="mock",
        lifecycle="COMPLETED",
    )
    workflow = WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="exec-1",
        workflow_name="support",
        workflow_version="v1",
        execution_status="COMPLETED",
        input={},
        final_state={},
        events=[],
    )
    history = ReplayEvaluationHistory(
        request=ReplayRequest(execution_id="exec-1"),
        history=EvaluationHistory(
            execution_id="exec-1",
            records=[
                EvaluationHistoryRecord(
                    evaluation_id="eval-1",
                    execution_id="exec-1",
                    evaluator_type="mock",
                    evaluator_version="1.0",
                    metrics=[],
                    metadata={},
                )
            ],
        ),
    )

    WorkflowExecutionOntologySynchronizer(service).synchronize(workflow)
    result = ReplayOntologySynchronizer(service).synchronize(history)

    assert result.succeeded is True
    assert service.find_relationships(
        "ReplayInvestigation",
        "replay:exec-1",
        direction="outgoing",
        relationship_type=RelationshipType.REPLAY_OF.value,
    )
