"""
Governance decision wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request

from ai_governance.api.dependencies.events import get_event_publisher
from ai_governance.api.dependencies.ontology import get_ontology_graph_query_service
from ai_governance.api.dependencies.repositories import (
    get_governance_decision_repository,
    get_policy_administration_repository,
)
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.events import EventPublisher


def get_decision_evidence_builder(
    graph_query_service: Any = Depends(get_ontology_graph_query_service),
) -> Any:
    """
    Create the decision evidence builder.
    """

    from ai_governance.decisions import DecisionEvidenceBuilder

    return DecisionEvidenceBuilder(graph_query_service)


def get_governance_policy_provider(
    policy_repository: Any = Depends(get_policy_administration_repository),
    configuration_service: Any = Depends(get_configuration_service),
) -> Any:
    """
    Create the policy provider used by governance reasoning.
    """

    from ai_governance.settings_control.policy_provider import (
        ConfiguredGovernancePolicyProvider,
    )

    return ConfiguredGovernancePolicyProvider(policy_repository, configuration_service)


def get_governance_reasoning_engine(
    evidence_builder: Any = Depends(get_decision_evidence_builder),
    policy_provider: Any = Depends(get_governance_policy_provider),
) -> Any:
    """
    Create the deterministic governance reasoning engine.
    """

    from ai_governance.decisions import (
        GovernancePolicyEvaluator,
        GovernanceReasoningEngine,
        ReasoningEvidenceSummarizer,
    )

    return GovernanceReasoningEngine(
        evidence_builder=evidence_builder,
        evidence_summarizer=ReasoningEvidenceSummarizer(),
        policy_evaluator=GovernancePolicyEvaluator(),
        policy_provider=policy_provider,
    )


def get_governance_decision_application_service(
    request: Request = None,
    reasoning_engine: Any = Depends(get_governance_reasoning_engine),
    decision_repository: Any = Depends(get_governance_decision_repository),
    evidence_builder: Any = Depends(get_decision_evidence_builder),
    graph_query_service: Any = Depends(get_ontology_graph_query_service),
    configuration_service: Any = Depends(get_configuration_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> Any:
    """
    Create the public governance decision application service.
    """

    from ai_governance.services.decision_application_service import (
        GovernanceDecisionApplicationService,
    )

    return GovernanceDecisionApplicationService(
        reasoning_engine=reasoning_engine,
        decision_repository=decision_repository,
        evidence_builder=evidence_builder,
        graph_query_service=graph_query_service,
        configuration_service=configuration_service,
        event_publisher=event_publisher,
        authorization_enforcers=tuple(
            getattr(request.app.state, "plugin_authorization_enforcers", ())
            if request is not None
            else ()
        ),
    )
