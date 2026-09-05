from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.causal_audit import (
    EvidenceInterventionPolicy,
    EvidenceInterventionPolicyStatus,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.repositories.sqlite.sqlite_evidence_intervention_policy_repository import (
    SQLiteEvidenceInterventionPolicyRepository,
)


def _policy(status=EvidenceInterventionPolicyStatus.DRAFT):
    now = datetime(2026, 8, 22, tzinfo=UTC)
    return EvidenceInterventionPolicy(
        "policy-a",
        1,
        "org-a",
        "project-a",
        status,
        "risk.lookup",
        "risk-schema",
        "1",
        "structured-json",
        "v1",
        (ControlledEvidenceStrategy.NULLIFY,),
        {"json_schema": {"type": "object"}, "neutral_value": {"records": []}},
        now,
        "operator",
        now if status is EvidenceInterventionPolicyStatus.ACTIVE else None,
        "operator" if status is EvidenceInterventionPolicyStatus.ACTIVE else None,
    )


def test_sqlite_persists_scope_and_protects_active_content(tmp_path):
    database = SQLiteDatabase(tmp_path / "intervention-policies.sqlite")
    database.initialize()
    repository = SQLiteEvidenceInterventionPolicyRepository(database)
    active = _policy().activate("operator", datetime(2026, 8, 22, tzinfo=UTC))
    repository.save(active)

    assert repository.get("policy-a", 1, "org-a", "project-a") == active
    assert repository.get("policy-a", 1, "org-b", "project-a") is None
    with pytest.raises(ValueError, match="immutable"):
        repository.save(
            replace(
                active,
                strategy_configuration={
                    "json_schema": {"type": "object"},
                    "neutral_value": {"records": ["x"]},
                },
                policy_digest="",
            )
        )

    retired = active.retire(datetime(2026, 8, 22, tzinfo=UTC))
    repository.save(retired)
    assert repository.list("org-a", "project-a") == [retired]
