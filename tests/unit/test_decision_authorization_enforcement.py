from __future__ import annotations

import pytest

from ai_governance.authorization.contracts import AuthorizationEnforcementDecision
from ai_governance.decisions import DecisionTargetType, DecisionType
from ai_governance.repositories.in_memory import InMemoryGovernanceDecisionRepository
from ai_governance.services.decision_application_service import (
    DecisionEvaluateCommand,
    GovernanceDecisionApplicationService,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.errors import AuthorizationDenied


def test_plugin_enforcer_blocks_governance_approval_before_evaluation() -> None:
    repository = InMemoryGovernanceDecisionRepository()
    enforcer = _DenyGovernanceApproval()
    service = GovernanceDecisionApplicationService(
        reasoning_engine=object(),
        decision_repository=repository,
        evidence_builder=object(),
        graph_query_service=object(),
        authorization_enforcers=(enforcer,),
    )

    with pytest.raises(AuthorizationDenied):
        service.evaluate(
            DecisionEvaluateCommand(
                target_type=DecisionTargetType.CANDIDATE,
                target_id="candidate-1",
                decision_type=DecisionType.APPROVE,
                context=TenantContext("org-1", "project-1", "actor-1", "request-1"),
            )
        )

    assert enforcer.requests == 1
    assert repository.list() == ()


class _DenyGovernanceApproval:
    def __init__(self) -> None:
        self.requests = 0

    def authorize(self, request):
        self.requests += 1
        assert request.action == "governance.decision.approve"
        assert request.resource.resource_type == "GovernanceDecision"
        assert request.resource.attributes == {"target_type": "Candidate"}
        return AuthorizationEnforcementDecision(False, "EXPLICIT_DENY_POLICY", "decision-1")
