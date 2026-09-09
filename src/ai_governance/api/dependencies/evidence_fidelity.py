from __future__ import annotations

from functools import lru_cache

from ai_governance.services.evidence_fidelity_service import EvidenceFidelityService


@lru_cache(maxsize=1)
def get_evidence_fidelity_service() -> EvidenceFidelityService:
    from ai_governance.api.dependencies.repositories import (
        get_agent_execution_repository,
        get_evidence_fidelity_comparison_repository,
    )

    runtime = get_agent_execution_repository()
    return EvidenceFidelityService(
        get_evidence_fidelity_comparison_repository(), runtime.execution, runtime.event
    )
