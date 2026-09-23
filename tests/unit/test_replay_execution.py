from datetime import UTC, datetime

import pytest

from ai_governance.domain.jobs import Job, JobExecutionContext, JobStatus, JobType
from ai_governance.domain.replay import (
    ControlledEvidenceIntervention,
    ControlledEvidenceStrategy,
    ReplayMode,
    ReplayStatus,
)
from ai_governance.domain.replay.errors import ReplayAdapterNotFound
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.repositories.in_memory_replay_repository import (
    InMemoryReplayRepository,
)
from ai_governance.services.replay_application_service import ReplayApplicationService
from ai_governance.services.replay_execution import (
    ReplayExecutionAdapterRegistry,
    ReplayJobHandler,
)
from ai_governance.spi.replay import (
    REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION,
    ReplayInterventionEnvelope,
)
from ai_governance.tenancy.domain import TenantContext


class _SourceResolver:
    def __init__(self, execution: WorkflowExecution) -> None:
        self.execution = execution

    def get_execution(self, execution_id: str, context: TenantContext):
        return self.execution if execution_id == self.execution.execution_id else None


class _Adapter:
    name = "historical"

    def __init__(self) -> None:
        self.intervention = None
        self.intervention_envelope = None

    def validate_configuration(self, source_execution, configuration) -> None:
        return None

    def replay(self, source_execution, configuration, context):
        self.intervention = context.controlled_evidence_intervention
        self.intervention_envelope = context.intervention_envelope
        return WorkflowExecution(
            workflow_id=source_execution.workflow_id,
            execution_id=context.new_execution_id,
            workflow_name=source_execution.workflow_name,
            workflow_version=source_execution.workflow_version,
            execution_status="COMPLETED",
            input=dict(source_execution.input),
            final_state={"replayed": True},
            events=[],
        )


class _Store:
    def __init__(self) -> None:
        self.executions: list[WorkflowExecution] = []

    def save(self, execution: WorkflowExecution) -> None:
        self.executions.append(execution)


def test_replay_job_handler_persists_new_execution_and_lineage() -> None:
    source = WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="source-1",
        workflow_name="workflow",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={"x": 1},
        final_state={},
        events=[],
        organization_id="organization-1",
        project_id="project-1",
    )
    repository = InMemoryReplayRepository()
    context = TenantContext("organization-1", "project-1", "actor-1", "request-1")
    replay = ReplayApplicationService(
        repository,
        _SourceResolver(source),
        id_generator=lambda: "replay-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    ).create(
        source_execution_id="source-1",
        context=context,
        idempotency_key="key-1",
        mode=ReplayMode.FULL,
    )
    replay = repository.update(
        replay.mark_queued("job-1", datetime(2026, 1, 1, tzinfo=UTC)), replay.version
    )
    registry = ReplayExecutionAdapterRegistry()
    registry.register(_Adapter())
    store = _Store()
    handler = ReplayJobHandler(
        repository,
        _SourceResolver(source),
        store,
        registry,
        execution_id_generator=lambda: "replay-execution-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = handler.handle(_job())

    assert result.status is JobStatus.SUCCEEDED
    assert store.executions[0].execution_id == "replay-execution-1"
    assert store.executions[0].metadata["source_execution_id"] == "source-1"
    assert (
        repository.get("replay-1", "organization-1", "project-1").status
        is ReplayStatus.EXECUTION_COMPLETED
    )


def test_replay_passes_typed_controlled_evidence_to_the_execution_adapter() -> None:
    source = WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="source-1",
        workflow_name="workflow",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={"x": 1},
        final_state={},
        events=[],
        organization_id="organization-1",
        project_id="project-1",
    )
    repository = InMemoryReplayRepository()
    context = TenantContext("organization-1", "project-1", "actor-1", "request-1")
    intervention = ControlledEvidenceIntervention(
        ControlledEvidenceStrategy.REPLACE,
        "causal-audit/v1",
        "artifact://evidence/original",
        "artifact://evidence/counterfactual",
        seed=7,
    )
    replay = ReplayApplicationService(
        repository,
        _SourceResolver(source),
        id_generator=lambda: "replay-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    ).create(
        source_execution_id="source-1",
        context=context,
        idempotency_key="key-1",
        controlled_evidence_intervention=intervention,
    )
    repository.update(
        replay.mark_queued("job-1", datetime(2026, 1, 1, tzinfo=UTC)), replay.version
    )
    adapter = _Adapter()
    registry = ReplayExecutionAdapterRegistry()
    registry.register(adapter)
    result = ReplayJobHandler(
        repository,
        _SourceResolver(source),
        _Store(),
        registry,
        execution_id_generator=lambda: "replay-execution-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    ).handle(_job())

    assert result.status is JobStatus.SUCCEEDED
    assert adapter.intervention == intervention
    assert adapter.intervention_envelope is None


def test_replay_passes_only_governed_intervention_metadata_to_an_external_adapter() -> (
    None
):
    source = WorkflowExecution(
        workflow_id="workflow-1",
        execution_id="source-1",
        workflow_name="workflow",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={},
        final_state={},
        events=[
            {
                "event_id": "tool-event-1",
                "runtime_tool_call_id": "provider-call-1",
                "evidence_references": ["runtime://protected-evidence"],
            }
        ],
        organization_id="organization-1",
        project_id="project-1",
        metadata={"external_execution_id": "external-run-1"},
    )
    repository = InMemoryReplayRepository()
    context = TenantContext("organization-1", "project-1", "actor-1", "request-1")
    intervention = ControlledEvidenceIntervention(
        ControlledEvidenceStrategy.REPLACE,
        "causal-audit/v1",
        "runtime://protected-evidence",
        counterfactual_evidence_reference="runtime://counterfactual/low-risk",
        target_event_id="tool-event-1",
        policy_id="risk-policy",
        policy_version=2,
        provider_id="opaque-reference",
        provider_version="v1",
        original_evidence_digest="sha256:original",
        counterfactual_evidence_digest="sha256:counterfactual",
    )
    replay = ReplayApplicationService(
        repository,
        _SourceResolver(source),
        id_generator=lambda: "replay-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    ).create(
        source_execution_id="source-1",
        context=context,
        idempotency_key="key-1",
        controlled_evidence_intervention=intervention,
    )
    repository.update(
        replay.mark_queued("job-1", datetime(2026, 1, 1, tzinfo=UTC)), replay.version
    )
    adapter = _Adapter()
    registry = ReplayExecutionAdapterRegistry()
    registry.register(adapter)

    result = ReplayJobHandler(
        repository,
        _SourceResolver(source),
        _Store(),
        registry,
        execution_id_generator=lambda: "replay-execution-1",
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    ).handle(_job())

    assert result.status is JobStatus.SUCCEEDED
    envelope = adapter.intervention_envelope
    assert envelope is not None
    assert envelope.policy_id == "risk-policy"
    assert envelope.policy_version == 2
    assert envelope.external_execution_id == "external-run-1"
    assert envelope.runtime_tool_call_id == "provider-call-1"
    assert envelope.intervention_provider == "opaque-reference"
    assert envelope.intervention_provider_version == "v1"
    assert envelope.strategy is ControlledEvidenceStrategy.REPLACE
    assert envelope.original_evidence_digest == "sha256:original"
    assert envelope.counterfactual_reference == "runtime://counterfactual/low-risk"
    assert envelope.counterfactual_digest == "sha256:counterfactual"
    assert envelope.intervention_digest == intervention.intervention_digest
    assert envelope.schema_version == REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION
    assert set(vars(envelope)) == {
        "policy_id",
        "policy_version",
        "external_execution_id",
        "runtime_tool_call_id",
        "intervention_provider",
        "intervention_provider_version",
        "strategy",
        "original_evidence_digest",
        "counterfactual_reference",
        "counterfactual_digest",
        "intervention_digest",
        "schema_version",
    }


def test_replay_intervention_envelope_v1_payload_round_trips_and_rejects_other_versions() -> (
    None
):
    envelope = ReplayInterventionEnvelope(
        policy_id="policy-1",
        policy_version=1,
        external_execution_id="external-1",
        runtime_tool_call_id="tool-call-1",
        intervention_provider="opaque-reference",
        intervention_provider_version="v1",
        strategy=ControlledEvidenceStrategy.REPLACE,
        original_evidence_digest="sha256:original",
        counterfactual_reference="runtime://counterfactual",
        counterfactual_digest="sha256:counterfactual",
        intervention_digest="sha256:intervention",
    )

    payload = envelope.to_payload()

    assert payload["schema_version"] == REPLAY_INTERVENTION_ENVELOPE_SCHEMA_VERSION
    assert ReplayInterventionEnvelope.from_payload(payload) == envelope
    with pytest.raises(ValueError, match="Unsupported Replay intervention envelope"):
        ReplayInterventionEnvelope.from_payload(
            {**payload, "schema_version": "replay-intervention-envelope/v2"}
        )
    with pytest.raises(ValueError, match="unsupported shape"):
        ReplayInterventionEnvelope.from_payload({**payload, "untrusted": "value"})


def test_unregistered_adapter_identifier_is_a_failed_lookup_not_a_dynamic_plugin_load() -> (
    None
):
    registry = ReplayExecutionAdapterRegistry()

    with pytest.raises(ReplayAdapterNotFound, match="unavailable"):
        registry.resolve("untrusted.module:install-and-run/v1")


def _job() -> Job:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Job(
        job_id="job-1",
        job_type=JobType.REPLAY_EXECUTION,
        status=JobStatus.RUNNING,
        input_refs={"replay_id": "replay-1"},
        input_hash="hash",
        idempotency_key="key",
        submitted_by="actor-1",
        attempt_count=1,
        max_attempts=3,
        result_ref=None,
        failure_reason=None,
        leased_by="worker-1",
        lease_expires_at=None,
        heartbeat_at=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
        execution_context=JobExecutionContext(
            "organization-1", "project-1", "actor-1", "request-1"
        ),
    )
