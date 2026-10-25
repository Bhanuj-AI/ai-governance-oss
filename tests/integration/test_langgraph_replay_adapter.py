"""Optional cross-repository proof for the independently released LangGraph adapter.

The OSS suite deliberately skips this module unless the external adapter is
installed. The adapter repository runs it with its source on ``PYTHONPATH``;
OSS itself never depends on, imports, or discovers a vendor runtime package.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

adapter_module = pytest.importorskip("aigp_langgraph_replay_adapter")

from aigp_langgraph_replay_adapter import (
    LangGraphReplayAdapter,
    SQLitePrivateSnapshotStore,
)
from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from tests.api.test_causal_audit_e2e_api import (
    _clear_dependencies,
    _record_execution,
    _run_causal_audit_worker,
)


def test_langgraph_adapter_completes_a_real_oss_causal_audit_without_mutation(
    tmp_path: Path,
) -> None:
    """REST execution evidence → manifest → worker → adapter → causal audit."""
    counterfactual_digest = "sha256:" + ("c" * 64)
    private_database = tmp_path / "langgraph-private-snapshots.db"
    banking_database = tmp_path / "banking.db"
    with sqlite3.connect(banking_database) as connection:
        connection.execute(
            "CREATE TABLE loan_applications (loan_id TEXT PRIMARY KEY, status TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO loan_applications VALUES ('LOAN-001', 'PENDING')"
        )

    _clear_dependencies()
    try:
        client = TestClient(create_app())
        execution_id = _record_execution(
            client,
            "langgraph-runtime",
            [[0.2, 0.2, 0.2]],
            replay_adapter_id="langgraph/v1",
            runtime_type="langgraph",
            replay_reference="langgraph://replays/causal-e2e-runtime",
            tool_name="banking.loan.approve",
            schema_id="banking-loan-status",
        )
        eligibility = client.get(
            f"/api/v1/agents-runtime/executions/{execution_id}/causal-audit-eligibility"
        )
        assert eligibility.status_code == 200
        manifest_hash = eligibility.json()["replay_manifest_hash"]
        assert isinstance(manifest_hash, str) and len(manifest_hash) == 64

        snapshots = SQLitePrivateSnapshotStore(private_database)
        snapshots.capture(
            replay_reference="langgraph://replays/causal-e2e-runtime",
            organization_id="org_default",
            project_id="project_default",
            external_execution_id="causal-e2e-langgraph-runtime",
            adapter_id="langgraph/v1",
            adapter_version="1",
            isolation_guarantee="runtime-isolated/v1",
            manifest_hash=manifest_hash,
            state={
                "baseline_score": 0.9,
                "counterfactual_scores": {counterfactual_digest: 0.2},
            },
        )
        policy_response = client.post(
            "/api/v1/agents-runtime/causal-audit/intervention-policies",
            json={
                "tool_name": "banking.loan.approve",
                "schema_id": "banking-loan-status",
                "schema_version": "1",
                "allowed_strategies": ["REPLACE"],
                "provider_id": "opaque-reference",
                "provider_version": "v1",
                "strategy_configuration": {
                    "counterfactual_reference": "langgraph://counterfactual/loan-001",
                    "counterfactual_digest": counterfactual_digest,
                    "runtime_attests_validation": True,
                },
            },
        )
        assert policy_response.status_code == 201, policy_response.text
        policy = policy_response.json()
        activated = client.post(
            "/api/v1/agents-runtime/causal-audit/intervention-policies/"
            f"{policy['policy_id']}/versions/{policy['version']}/activate"
        )
        assert activated.status_code == 200
        audit_response = client.post(
            "/api/v1/agents-runtime/causal-audits",
            json={
                "execution_id": execution_id,
                "evaluator_ref": "recorded-outcome/v1",
                "intervention": {
                    "strategy": "REPLACE",
                    "counterfactual_samples": 1,
                    "intervention_policy_id": policy["policy_id"],
                    "intervention_policy_version": policy["version"],
                },
            },
        )
        assert audit_response.status_code == 202, audit_response.text

        _run_causal_audit_worker(LangGraphReplayAdapter(snapshots))

        audit = client.get(
            f"/api/v1/agents-runtime/causal-audits/{audit_response.json()['audit_id']}"
        )
        assert audit.status_code == 200
        assert audit.json()["status"] == "SUCCEEDED"
        assert audit.json()["classification"] == "EVIDENCE_ALIGNED"
        with sqlite3.connect(banking_database) as connection:
            assert (
                connection.execute(
                    "SELECT status FROM loan_applications WHERE loan_id = 'LOAN-001'"
                ).fetchone()[0]
                == "PENDING"
            )
    finally:
        _clear_dependencies()
