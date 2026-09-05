from datetime import UTC, datetime

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.causal_audit import (
    CausalAudit,
    CausalAuditClassification,
    CausalAuditStatus,
    CounterfactualReplayLineage,
    EvidenceInterventionStrategy,
    InterventionConfiguration,
    OutcomeScore,
    ToolEvidenceInfluence,
)
from ai_governance.repositories.causal_audit_repository import CausalAuditListFilters
from ai_governance.repositories.sqlite.sqlite_causal_audit_repository import (
    SQLiteCausalAuditRepository,
)


def _audit(audit_id: str, organization_id: str = "org-a") -> CausalAudit:
    now = datetime(2026, 8, 19, tzinfo=UTC)
    return CausalAudit(
        audit_id,
        organization_id,
        "project-a",
        "execution-a",
        "agent-a",
        CausalAuditStatus.QUEUED,
        "causal-audit/v1",
        "recorded-outcome/v1",
        InterventionConfiguration(EvidenceInterventionStrategy.REPLACE, 3),
        f"fingerprint-{audit_id}",
        "auditor",
        now,
        now,
    )


def test_sqlite_causal_audits_are_tenant_scoped_and_immutable(tmp_path):
    database = SQLiteDatabase(tmp_path / "causal-audit.sqlite")
    database.initialize()
    repository = SQLiteCausalAuditRepository(database)
    queued = _audit("audit-a")
    repository.save(queued)

    running = queued.mark_running(queued.created_at)
    repository.save(running, expected_version=queued.version)
    completed = running.mark_succeeded(
        CausalAuditClassification.NO_TOOL_EVIDENCE,
        (),
        {"result_digest": "digest"},
        running.created_at,
    )
    repository.save(completed, expected_version=running.version)

    assert (
        repository.get("audit-a", "org-a", "project-a").classification
        is CausalAuditClassification.NO_TOOL_EVIDENCE
    )
    assert repository.get("audit-a", "org-b", "project-a") is None
    assert repository.list(
        CausalAuditListFilters(
            classification=CausalAuditClassification.NO_TOOL_EVIDENCE
        ),
        "org-a",
        "project-a",
    ) == [completed]

    try:
        repository.save(completed.mark_cancelled(completed.completed_at))
    except ValueError as error:
        assert "immutable" in str(error)
    else:
        raise AssertionError("terminal audit update must be rejected")


def test_sqlite_round_trips_complete_counterfactual_lineage(tmp_path):
    database = SQLiteDatabase(tmp_path / "causal-audit-lineage.sqlite")
    database.initialize()
    repository = SQLiteCausalAuditRepository(database)
    now = datetime(2026, 8, 19, tzinfo=UTC)
    intervention = InterventionConfiguration(
        EvidenceInterventionStrategy.REPLACE,
        1,
        intervention_policy_id="policy-a",
        intervention_policy_version=1,
    )
    score = OutcomeScore(0.2, "outcome", "test-evaluator", "v1")
    lineage = CounterfactualReplayLineage(
        replay_id="replay-a",
        replay_execution_id="execution-a",
        replay_status="EXECUTION_COMPLETED",
        policy_id="policy-a",
        policy_version=1,
        provider_id="structured-json",
        provider_version="v1",
        original_evidence_digest="sha256:original",
        counterfactual_evidence_reference="counterfactual:sha256:replacement",
        counterfactual_evidence_digest="sha256:replacement",
        intervention_digest="intervention-digest",
        evaluator_score=score,
    )
    queued = CausalAudit(
        "audit-lineage",
        "org-a",
        "project-a",
        "source-execution-a",
        "agent-a",
        CausalAuditStatus.QUEUED,
        "causal-audit/v1",
        "test-evaluator/v1",
        intervention,
        "fingerprint-lineage",
        "auditor",
        now,
        now,
    )
    repository.save(queued)
    running = queued.mark_running(now)
    repository.save(running, expected_version=queued.version)
    completed = running.mark_succeeded(
        CausalAuditClassification.EVIDENCE_ALIGNED,
        (
            ToolEvidenceInfluence(
                tool_call_id="call-a",
                tool_name="lookup",
                position=0,
                intervention=intervention,
                counterfactual_count=1,
                baseline_score=OutcomeScore(
                    0.9, "outcome", "test-evaluator", "v1"
                ),
                counterfactual_score=score,
                influence_score=0.7,
                useful=True,
                harmful=False,
                post_saturation=False,
                counterfactual_replay_ids=("replay-a",),
                counterfactual_execution_ids=("execution-a",),
                counterfactual_lineage=(lineage,),
            ),
        ),
        {"result_digest": "digest"},
        now,
    )
    repository.save(completed, expected_version=running.version)

    stored = repository.get("audit-lineage", "org-a", "project-a")
    assert stored is not None
    restored = stored.tool_call_results[0].counterfactual_lineage[0]
    assert restored.intervention_digest == "intervention-digest"
    assert restored.evaluator_score.value == 0.2
    assert restored.replay_execution_id == "execution-a"
