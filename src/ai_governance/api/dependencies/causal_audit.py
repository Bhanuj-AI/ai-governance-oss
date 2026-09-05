from __future__ import annotations

from functools import lru_cache

from ai_governance.services.causal_audit_service import CausalAuditService


def causal_audit_list_filters(**kwargs):
    """Keep persistence-neutral list-filter construction out of REST routers."""
    from ai_governance.repositories.causal_audit_repository import (
        CausalAuditListFilters,
    )

    return CausalAuditListFilters(**kwargs)


@lru_cache(maxsize=1)
def get_causal_audit_service() -> CausalAuditService:
    from ai_governance.api.dependencies.agent_execution import (
        get_agent_execution_repository,
    )
    from ai_governance.api.dependencies.evidence_intervention_policy import (
        get_evidence_intervention_policy_service,
        get_governed_counterfactual_generator,
    )
    from ai_governance.api.dependencies.replay import get_replay_source_resolver
    from ai_governance.api.dependencies.repositories import (
        get_causal_audit_repository,
        get_job_repository,
        get_replay_repository,
    )
    from ai_governance.api.dependencies.runtime_finding_repo import (
        get_runtime_finding_repository,
    )
    from ai_governance.services.agent_runtime_controlled_replay import (
        AgentRuntimeReplaySourceBridge,
    )
    from ai_governance.services.job_api_service import JobApiService
    from ai_governance.services.replay_application_service import (
        ReplayApplicationService,
    )

    execution_repositories = get_agent_execution_repository()
    jobs = JobApiService(get_job_repository())
    replay_source = get_replay_source_resolver()
    return CausalAuditService(
        get_causal_audit_repository(),
        execution_repositories.execution,
        execution_repositories.event,
        jobs,
        finding_repository=get_runtime_finding_repository(),
        replay_application_service=ReplayApplicationService(
            replay_repository=get_replay_repository(),
            source_resolver=replay_source,
            job_service=jobs,
        ),
        replay_repository=get_replay_repository(),
        replay_source_bridge=AgentRuntimeReplaySourceBridge(replay_source),
        replay_execution_store=replay_source,
        intervention_policy_service=get_evidence_intervention_policy_service(),
        counterfactual_generator=get_governed_counterfactual_generator(),
    )
