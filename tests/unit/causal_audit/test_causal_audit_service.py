from dataclasses import dataclass
from datetime import UTC, datetime

from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.domain.causal_audit import (
    CausalAuditClassification,
    EvidenceInterventionStrategy,
    InterventionConfiguration,
)
from ai_governance.domain.jobs import Job, JobExecutionContext, JobStatus, JobType
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.repositories.in_memory import InMemoryJobRepository
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.repositories.in_memory.in_memory_causal_audit_repository import (
    InMemoryCausalAuditRepository,
)
from ai_governance.repositories.in_memory.in_memory_evidence_intervention_policy_repository import (
    InMemoryEvidenceInterventionPolicyRepository,
)
from ai_governance.repositories.in_memory_replay_repository import (
    InMemoryReplayRepository,
)
from ai_governance.services.agent_runtime_controlled_replay import (
    AgentRuntimeReplaySourceBridge,
    DeterministicAgentRuntimeReplayAdapter,
)
from ai_governance.services.causal_audit_service import (
    CausalAuditJobHandler,
    CausalAuditNotEligible,
    CausalAuditService,
    CausalAuditSettings,
)
from ai_governance.services.job_api_service import JobApiService
from ai_governance.services.evidence_intervention_policy_service import (
    EvidenceInterventionPolicyService,
)
from ai_governance.services.evidence_interventions import (
    EvidenceInterventionProviderRegistry,
    GovernedCounterfactualGenerator,
    InMemoryEvidenceValueResolver,
    StructuredJsonEvidenceInterventionProvider,
)
from ai_governance.services.job_executor import JobExecutor
from ai_governance.services.replay_application_service import ReplayApplicationService
from ai_governance.services.replay_execution import (
    ReplayExecutionAdapterRegistry,
    ReplayJobHandler,
)
from ai_governance.services.replay_execution_discovery import (
    InMemoryReplaySourceResolver,
)
from ai_governance.services.synthetic_agent_runtime_replay import (
    SyntheticAgentRuntimeReplayAdapter,
    SyntheticReplayHttpResponse,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.workers.job_worker import JobWorker


NOW = datetime(2026, 8, 19, tzinfo=UTC)
CONTEXT = TenantContext("org-a", "project-a", "auditor", "request-a")


@dataclass
class _Setup:
    service: CausalAuditService
    replay_worker: JobWorker


def _service(
    counterfactual_scores: list[float],
    tool_calls: int = 1,
    baseline_score: float = 0.9,
    replay_capable: bool = True,
    settings: CausalAuditSettings | None = None,
    replacement_count: int = 1,
    replay_adapter=None,
) -> _Setup:
    adapter_id = (
        replay_adapter.name if replay_adapter is not None else "deterministic-agent-runtime/v1"
    )
    runtime_type = (
        "synthetic-agent-runtime" if replay_adapter is not None else "deterministic"
    )
    executions = InMemoryAgentExecutionRepository()
    events = InMemoryAgentExecutionEventRepository()
    executions.save(
        AgentExecution(
            "execution-a",
            "org-a",
            "project-a",
            "agent-a",
            "Agent A",
            "v1",
            "external-a",
            runtime_type,
            AgentExecutionStatus.SUCCEEDED,
            NOW,
            NOW,
            None,
            None,
            NOW,
            NOW,
            metadata=(
                {
                    "replay_capability": {
                        "runtime_type": runtime_type,
                        "adapter_id": adapter_id,
                        "adapter_version": "1",
                        "replay_reference": (
                            "synthetic://replays/execution-a"
                            if replay_adapter is not None
                            else "artifact://execution-a"
                        ),
                        "supported_interventions": ["REPLACE"],
                        **(
                            {
                                "metadata": {
                                    "endpoint": "https://synthetic.example.test/replay"
                                }
                            }
                            if replay_adapter is not None
                            else {}
                        ),
                    }
                }
                if replay_capable
                else {}
            ),
        )
    )
    resolver = InMemoryEvidenceValueResolver(
        {
            ("org-a", "project-a", f"artifact://evidence/{index}"): {"value": index}
            for index in range(tool_calls)
        }
        | {
            ("org-a", "project-a", f"artifact://replacement/{index}"): {
                "value": -index - 1
            }
            for index in range(replacement_count)
        }
    )
    for index in range(tool_calls):
        evidence_ref = f"artifact://evidence/{index}"
        events.save(
            AgentExecutionEvent(
                f"tool-{index}",
                "execution-a",
                "org-a",
                "project-a",
                EventType.TOOL_CALL,
                index,
                NOW,
                NOW,
                None,
                None,
                f"tool-{index}",
                ActorType.TOOL,
                evidence_references=(evidence_ref,),
                attributes={
                    "tool": "lookup",
                    "causal_replay": {
                        "counterfactual_outcomes_by_digest": {
                            resolver.digest(
                                {"value": -replacement_index - 1}
                            ): counterfactual_scores
                            for replacement_index in range(replacement_count)
                        },
                        "evidence_descriptor": {
                            "tool_name": "lookup",
                            "evidence_ref": evidence_ref,
                            "evidence_digest": resolver.digest({"value": index}),
                            "content_type": "application/json",
                            "schema_id": "lookup-result",
                            "schema_version": "1",
                            "replay_adapter_id": adapter_id,
                            "metadata": {
                                "external_tool_call_id": f"execution-a:tool:{index}"
                            },
                        },
                    },
                },
            )
        )
    events.save(
        AgentExecutionEvent(
            "evaluation",
            "execution-a",
            "org-a",
            "project-a",
            EventType.EVALUATION,
            tool_calls + 1,
            NOW,
            NOW,
            None,
            None,
            "scorer",
            ActorType.EVALUATOR,
            attributes={"score": baseline_score},
        )
    )
    jobs = InMemoryJobRepository()
    job_service = JobApiService(jobs)
    replays = InMemoryReplayRepository()
    source_store = InMemoryReplaySourceResolver()
    replay_application = ReplayApplicationService(
        replay_repository=replays,
        source_resolver=source_store,
        job_service=job_service,
        id_generator=_replay_id,
    )
    policy_service = EvidenceInterventionPolicyService(
        InMemoryEvidenceInterventionPolicyRepository(),
        EvidenceInterventionProviderRegistry(
            (StructuredJsonEvidenceInterventionProvider(resolver),)
        ),
        id_generator=lambda: "policy-a",
        clock=lambda: NOW,
    )
    policy = policy_service.create_draft(
        tool_name="lookup",
        schema_id="lookup-result",
        schema_version="1",
        provider_id="structured-json",
        provider_version="v1",
        allowed_strategies=(ControlledEvidenceStrategy.REPLACE,),
        strategy_configuration={
            "json_schema": {"type": "object"},
            "replacement_references": [
                f"artifact://replacement/{index}" for index in range(replacement_count)
            ],
        },
        context=CONTEXT,
    )
    policy_service.activate(policy.policy_id, policy.version, CONTEXT)
    service = CausalAuditService(
        InMemoryCausalAuditRepository(),
        executions,
        events,
        job_service,
        settings=settings,
        id_generator=lambda: "audit-a",
        replay_application_service=replay_application,
        replay_repository=replays,
        replay_source_bridge=AgentRuntimeReplaySourceBridge(source_store),
        replay_execution_store=source_store,
        counterfactual_generator=GovernedCounterfactualGenerator(
            policy_service,
            EvidenceInterventionProviderRegistry(
                (StructuredJsonEvidenceInterventionProvider(resolver),)
            ),
            resolver,
        ),
        intervention_policy_service=policy_service,
    )
    registry = ReplayExecutionAdapterRegistry()
    registry.register(replay_adapter or DeterministicAgentRuntimeReplayAdapter())
    replay_handler = ReplayJobHandler(
        replays,
        source_store,
        source_store,
        registry,
        execution_id_generator=_execution_id,
    )
    return _Setup(
        service,
        JobWorker(
            "controlled-replay-worker",
            jobs,
            JobExecutor({JobType.REPLAY_EXECUTION: replay_handler}),
            job_types=(JobType.REPLAY_EXECUTION,),
        ),
    )


def _run(setup: _Setup):
    audit = setup.service.start(
        "execution-a",
        "recorded-outcome/v1",
        InterventionConfiguration(
            EvidenceInterventionStrategy.REPLACE,
            3,
            intervention_policy_id="policy-a",
            intervention_policy_version=1,
        ),
        CONTEXT,
    )
    pending = setup.service.execute(audit.audit_id, CONTEXT)
    assert pending.status.value == "RUNNING"
    while setup.replay_worker.run_once() is not None:
        pass
    return setup.service.execute(audit.audit_id, CONTEXT)


def _replay_id():
    _replay_id.value += 1
    return f"replay-{_replay_id.value}"


_replay_id.value = 0


def _execution_id():
    _execution_id.value += 1
    return f"counterfactual-{_execution_id.value}"


_execution_id.value = 0


def test_classifies_evidence_ignored_from_worker_executed_replays():
    audit = _run(_service([0.9, 0.9, 0.9]))
    assert audit.classification is CausalAuditClassification.EVIDENCE_IGNORED
    assert audit.tool_call_results[0].influence_score == 0.0
    assert len(audit.tool_call_results[0].counterfactual_replay_ids) == 1
    provenance = audit.tool_call_results[0].diagnostics["intervention_provenance"]
    assert provenance["policy_id"] == "policy-a"
    assert provenance["provider_id"] == "structured-json"
    assert provenance["counterfactual_evidence_digest"].startswith("sha256:")


def test_classifies_evidence_aligned_when_replay_changes_score_and_agent_stops():
    audit = _run(_service([0.1, 0.2, 0.3]))
    assert audit.classification is CausalAuditClassification.EVIDENCE_ALIGNED
    assert audit.tool_call_results[0].useful is True
    assert len(audit.tool_call_results[0].counterfactual_execution_ids) == 1


def test_causal_audit_consumes_successful_synthetic_runtime_replay():
    class _Transport:
        def post(self, _endpoint, payload, _headers, _timeout):
            return SyntheticReplayHttpResponse(
                200,
                {
                    "execution_status": "COMPLETED",
                    "isolated": True,
                    "replay_reference": "synthetic://replays/execution-a",
                    "intervention": "REPLACE",
                    "external_execution_id": payload["external_execution_id"],
                    "external_tool_call_id": payload["external_tool_call_id"],
                    "source_evidence_digest": payload["source_evidence_digest"],
                    "outcome_score": 0.1,
                },
            )

    adapter = SyntheticAgentRuntimeReplayAdapter(
        approved_endpoint="https://synthetic.example.test/replay",
        transport=_Transport(),
        token_provider=lambda: None,
    )

    audit = _run(_service([0.9], replay_adapter=adapter))

    assert audit.classification is CausalAuditClassification.EVIDENCE_ALIGNED
    lineage = audit.tool_call_results[0].counterfactual_lineage[0]
    assert lineage.replay_status == "EXECUTION_COMPLETED"


def test_classifies_over_extended_after_saturation():
    audit = _run(_service([0.1, 0.2, 0.3], tool_calls=2))
    assert audit.classification is CausalAuditClassification.OVER_EXTENDED
    assert audit.tool_call_results[1].post_saturation is True


def test_rejects_cross_tenant_execution_without_disclosure():
    setup = _service([0.1, 0.2, 0.3])
    result = setup.service.eligibility(
        "execution-a", TenantContext("org-b", "project-b", "auditor", "request-b")
    )
    assert result.code.value == "NOT_REPLAYABLE"


def test_exact_influence_threshold_is_material():
    audit = _run(
        _service(
            [0.5, 0.5, 0.5],
            baseline_score=1.0,
            settings=CausalAuditSettings(influence_threshold=0.5),
        )
    )
    assert audit.tool_call_results[0].influence_score == 0.5
    assert audit.tool_call_results[0].useful is True
    assert audit.classification is CausalAuditClassification.EVIDENCE_ALIGNED


def test_partial_counterfactual_failure_fails_without_fabricating_influence():
    audit = _run(_service([0.1, 0.2], replacement_count=3))
    assert audit.status.value == "FAILED"
    assert audit.failure_code == "INSUFFICIENT_COUNTERFACTUAL_EVIDENCE"
    assert audit.tool_call_results == ()


def test_start_and_worker_redelivery_are_idempotent():
    setup = _service([0.1, 0.2, 0.3])
    intervention = InterventionConfiguration(
        EvidenceInterventionStrategy.REPLACE,
        3,
        intervention_policy_id="policy-a",
        intervention_policy_version=1,
    )
    first = setup.service.start(
        "execution-a", "recorded-outcome/v1", intervention, CONTEXT
    )
    repeated = setup.service.start(
        "execution-a", "recorded-outcome/v1", intervention, CONTEXT
    )
    setup.service.execute(first.audit_id, CONTEXT)
    while setup.replay_worker.run_once() is not None:
        pass
    completed = setup.service.execute(first.audit_id, CONTEXT)
    assert repeated.audit_id == first.audit_id
    assert setup.service.execute(first.audit_id, CONTEXT) == completed


def test_worker_handler_retry_reuses_completed_audit_result():
    setup = _service([0.1, 0.2, 0.3])
    audit = setup.service.start(
        "execution-a",
        "recorded-outcome/v1",
        InterventionConfiguration(
            EvidenceInterventionStrategy.REPLACE,
            3,
            intervention_policy_id="policy-a",
            intervention_policy_version=1,
        ),
        CONTEXT,
    )
    job = Job(
        "job-a",
        JobType.CAUSAL_AUDIT,
        JobStatus.RUNNING,
        {"audit_id": audit.audit_id},
        "input-hash",
        "idempotency-key",
        "auditor",
        1,
        3,
        None,
        None,
        None,
        None,
        None,
        NOW,
        NOW,
        NOW,
        None,
        JobExecutionContext("org-a", "project-a", "auditor", "request-a"),
    )
    handler = CausalAuditJobHandler(setup.service)
    first = handler.handle(job)
    while setup.replay_worker.run_once() is not None:
        pass
    completed = handler.handle(job)
    assert first.status is JobStatus.SUCCEEDED
    assert completed.status is JobStatus.SUCCEEDED
    assert handler.handle(job).result_ref == completed.result_ref


def test_cross_tenant_start_cannot_probe_execution():
    setup = _service([0.1, 0.2, 0.3])
    try:
        setup.service.start(
            "execution-a",
            "recorded-outcome/v1",
            InterventionConfiguration(
                EvidenceInterventionStrategy.REPLACE,
                3,
                intervention_policy_id="policy-a",
                intervention_policy_version=1,
            ),
            TenantContext("org-b", "project-b", "auditor", "request-b"),
        )
    except CausalAuditNotEligible as error:
        assert "NOT_REPLAYABLE" in str(error)
    else:
        raise AssertionError("cross-tenant audit should fail closed")


def test_missing_explicit_replay_capability_fails_closed():
    result = _service([0.1, 0.2, 0.3], replay_capable=False).service.eligibility(
        "execution-a",
        CONTEXT,
        intervention_policy_id="policy-a",
        intervention_policy_version=1,
    )
    assert result.code.value == "UNSUPPORTED_TOOL"
