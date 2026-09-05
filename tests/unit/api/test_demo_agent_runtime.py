"""Tests for the agent runtime demo seed module."""

from __future__ import annotations

import pytest

from ai_governance.api.demo_agent_runtime import (
    seed_agent_runtime_data,
)
from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.agent_execution import AgentExecutionStatus
from ai_governance.domain.runtime_findings.finding import FindingSeverity, FindingStatus
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.repositories.in_memory.in_memory_evidence_intervention_policy_repository import (
    InMemoryEvidenceInterventionPolicyRepository,
)
from ai_governance.repositories.in_memory.in_memory_runtime_finding_repository import (
    InMemoryRuntimeFindingRepository,
)
from ai_governance.repositories.sqlite.sqlite_agent_execution_repository import (
    SQLiteAgentExecutionEventRepository,
    SQLiteAgentExecutionRepository,
)
from ai_governance.repositories.sqlite.sqlite_runtime_finding_repository import (
    SQLiteRuntimeFindingRepository,
)


@pytest.fixture()
def repos():
    return (
        InMemoryAgentExecutionRepository(),
        InMemoryAgentExecutionEventRepository(),
        InMemoryRuntimeFindingRepository(),
    )


class TestSeedAgentRuntimeData:
    """Test the demo seed for agent runtime data."""

    def test_seeds_executions_and_findings(self, repos):
        execution_repo, event_repo, finding_repo = repos
        result = seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        assert len(result["execution_ids"]) > 0
        assert len(result["finding_ids"]) > 0

        # Verify executions were created
        all_execs = execution_repo.list(
            type(
                "F",
                (),
                {
                    "agent_id": None,
                    "status": None,
                    "runtime_provider": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )
        demo_execs = [e for e in all_execs if e.execution_id.startswith("demo-exec-")]
        assert len(demo_execs) == len(result["execution_ids"])

    def test_seeds_active_synthetic_runtime_intervention_policies(self, repos):
        execution_repo, event_repo, finding_repo = repos
        policies = InMemoryEvidenceInterventionPolicyRepository()

        first = seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            intervention_policy_repo=policies,
            organization_id="org_test",
            project_id="project_test",
        )
        second = seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            intervention_policy_repo=policies,
            organization_id="org_test",
            project_id="project_test",
        )

        seeded = policies.list("org_test", "project_test")
        assert len(first["intervention_policy_ids"]) == 13
        assert second["intervention_policy_ids"] == []
        assert len(seeded) == 13
        assert all(item.status.value == "ACTIVE" for item in seeded)
        assert all(item.provider_id == "opaque-reference" for item in seeded)

    def test_covers_all_execution_statuses(self, repos):
        execution_repo, event_repo, finding_repo = repos
        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        all_execs = execution_repo.list(
            type(
                "F",
                (),
                {
                    "agent_id": None,
                    "status": None,
                    "runtime_provider": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )
        demo_execs = [e for e in all_execs if e.execution_id.startswith("demo-exec-")]
        statuses = {e.status for e in demo_execs}

        # Should have at least SUCCEEDED, FAILED, CANCELLED, RUNNING, RECEIVED
        assert AgentExecutionStatus.SUCCEEDED in statuses
        assert AgentExecutionStatus.FAILED in statuses
        assert AgentExecutionStatus.CANCELLED in statuses
        assert AgentExecutionStatus.RUNNING in statuses
        assert AgentExecutionStatus.RECEIVED in statuses

    def test_covers_multiple_agents_and_runtimes(self, repos):
        execution_repo, event_repo, finding_repo = repos
        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        all_execs = execution_repo.list(
            type(
                "F",
                (),
                {
                    "agent_id": None,
                    "status": None,
                    "runtime_provider": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )
        demo_execs = [e for e in all_execs if e.execution_id.startswith("demo-exec-")]
        agents = {e.agent_id for e in demo_execs}
        runtimes = {e.runtime_provider for e in demo_execs}

        assert len(agents) >= 4
        assert len(runtimes) >= 3

    def test_covers_all_finding_severities(self, repos):
        execution_repo, event_repo, finding_repo = repos
        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        all_findings = finding_repo.list(
            type(
                "F",
                (),
                {
                    "finding_type": None,
                    "subject_type": None,
                    "subject_id": None,
                    "severity": None,
                    "status": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )
        demo_findings = [
            f for f in all_findings if f.finding_id.startswith("demo-finding-")
        ]
        severities = {f.severity for f in demo_findings}

        assert FindingSeverity.CRITICAL in severities
        assert FindingSeverity.HIGH in severities
        assert FindingSeverity.MEDIUM in severities
        assert FindingSeverity.LOW in severities
        assert FindingSeverity.INFO in severities

    def test_covers_open_and_resolved_findings(self, repos):
        execution_repo, event_repo, finding_repo = repos
        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        all_findings = finding_repo.list(
            type(
                "F",
                (),
                {
                    "finding_type": None,
                    "subject_type": None,
                    "subject_id": None,
                    "severity": None,
                    "status": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )
        demo_findings = [
            f for f in all_findings if f.finding_id.startswith("demo-finding-")
        ]
        statuses = {f.status for f in demo_findings}

        assert FindingStatus.OPEN in statuses
        assert FindingStatus.RESOLVED in statuses

    def test_is_idempotent(self, repos):
        execution_repo, event_repo, finding_repo = repos

        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )
        count_after_first = execution_repo.list(
            type(
                "F",
                (),
                {
                    "agent_id": None,
                    "status": None,
                    "runtime_provider": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )

        result2 = seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        count_after_second = execution_repo.list(
            type(
                "F",
                (),
                {
                    "agent_id": None,
                    "status": None,
                    "runtime_provider": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )

        # Second call should return empty lists (already seeded)
        assert result2["execution_ids"] == []
        assert result2["finding_ids"] == []
        # Count should be the same
        assert len(count_after_first) == len(count_after_second)

    def test_repairs_a_partially_seeded_execution(self, repos):
        execution_repo, event_repo, finding_repo = repos

        first = seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )
        execution_id = first["execution_ids"][0]
        event_repo._events_by_id.clear()
        event_repo._events_by_execution.clear()

        retry = seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        assert execution_id in retry["execution_ids"]
        assert event_repo.list_by_execution(execution_id, "org_test", "project_test")

    def test_seeds_and_retries_against_sqlite(self, tmp_path):
        database = SQLiteDatabase(tmp_path / "agent-runtime.db")
        database.initialize()
        execution_repo = SQLiteAgentExecutionRepository(database)
        event_repo = SQLiteAgentExecutionEventRepository(database)
        finding_repo = SQLiteRuntimeFindingRepository(database)

        first = seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )
        second = seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        assert first["execution_ids"]
        assert first["finding_ids"]
        assert second == {"execution_ids": [], "finding_ids": []}

    def test_executions_have_events(self, repos):
        execution_repo, event_repo, finding_repo = repos
        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        all_execs = execution_repo.list(
            type(
                "F",
                (),
                {
                    "agent_id": None,
                    "status": None,
                    "runtime_provider": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )
        demo_execs = [e for e in all_execs if e.execution_id.startswith("demo-exec-")]

        # Each demo execution should have at least 1 event
        for exec_item in demo_execs:
            events = event_repo.list_by_execution(
                exec_item.execution_id,
                "org_test",
                "project_test",
            )
            assert len(events) >= 1, f"Execution {exec_item.execution_id} has no events"

    def test_causal_audit_examples_publish_schema_described_tool_evidence(self, repos):
        execution_repo, event_repo, finding_repo = repos
        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        events = event_repo.list_by_execution(
            "demo-exec-ext-fraud-001", "org_test", "project_test"
        )
        tool_events = [event for event in events if event.event_type.value == "TOOL_CALL"]

        assert [event.attributes["tool"] for event in tool_events] == [
            "query_transaction_db",
            "lookup_history",
            "verify_merchant",
        ]
        assert [
            event.attributes["causal_replay"]["evidence_descriptor"]["schema_id"]
            for event in tool_events
        ] == ["transaction-record", "account-history", "merchant-verification"]
        assert all(event.evidence_references for event in tool_events)

        for execution_id in (
            "demo-exec-ext-claims-001",
            "demo-exec-ext-fraud-001",
            "demo-exec-ext-fraud-002",
            "demo-exec-ext-compliance-001",
            "demo-exec-ext-orch-001",
            "demo-exec-ext-fraud-policy-source-001",
        ):
            for event in event_repo.list_by_execution(
                execution_id, "org_test", "project_test"
            ):
                if event.event_type.value != "TOOL_CALL":
                    continue
                descriptor = event.attributes["causal_replay"]["evidence_descriptor"]
                assert descriptor["tool_name"] == event.attributes["tool"]
                assert descriptor["schema_id"]
                assert descriptor["schema_version"]
                assert descriptor["metadata"]["json_schema"]["properties"]
                assert event.evidence_references == (descriptor["evidence_ref"],)

    def test_replay_capable_demo_source_declares_controlled_replay_contract(self, repos):
        execution_repo, event_repo, finding_repo = repos
        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        execution = execution_repo.get(
            "demo-exec-ext-fraud-replay-source-001", "org_test", "project_test"
        )
        assert execution is not None
        capability = execution.metadata["replay_capability"]
        assert capability["adapter_id"] == "deterministic-agent-runtime/v1"
        assert capability["supported_interventions"] == ["PERTURB"]

        events = event_repo.list_by_execution(
            execution.execution_id, "org_test", "project_test"
        )
        tool_event = next(event for event in events if event.event_type.value == "TOOL_CALL")
        replay = tool_event.attributes["causal_replay"]
        assert replay["evidence_descriptor"]["evidence_digest"].startswith("sha256:")
        assert replay["counterfactual_outcomes_by_digest"]

    def test_finding_has_consecutive_normal_windows(self, repos):
        execution_repo, event_repo, finding_repo = repos
        seed_agent_runtime_data(
            execution_repo,
            event_repo,
            finding_repo,
            organization_id="org_test",
            project_id="project_test",
        )

        all_findings = finding_repo.list(
            type(
                "F",
                (),
                {
                    "finding_type": None,
                    "subject_type": None,
                    "subject_id": None,
                    "severity": None,
                    "status": None,
                    "created_after": None,
                    "created_before": None,
                    "limit": 100,
                },
            )(),
            "org_test",
            "project_test",
        )
        demo_findings = [
            f for f in all_findings if f.finding_id.startswith("demo-finding-")
        ]

        # Only the dedicated reconciliation fixture carries durable proof;
        # presentation-only findings never invent recovery progress.
        progressed = [f for f in demo_findings if f.consecutive_normal_windows > 0]
        assert len(progressed) == 1
        assert progressed[0].finding_id == "demo-finding-reconcile-ready"
        assert len(progressed[0].healthy_reconciliation_windows) == 1

        # The resolved finding is retained for lifecycle presentation.
        resolved = [f for f in demo_findings if f.status == FindingStatus.RESOLVED]
        assert len(resolved) >= 1
        assert resolved[0].consecutive_normal_windows == 0
