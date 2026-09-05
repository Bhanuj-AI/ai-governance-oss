"""Provider SPI for deterministic, governed counterfactual evidence."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from ai_governance.domain.causal_audit import (
    CounterfactualEvidence,
    EvidenceInterventionPolicy,
    ToolEvidenceDescriptor,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.tenancy.domain import TenantContext



class EvidenceInterventionProvider(Protocol):
    provider_id: str
    provider_version: str

    def supports(
        self, descriptor: ToolEvidenceDescriptor, strategy: ControlledEvidenceStrategy
    ) -> bool: ...

    def validate_policy(
        self, policy: EvidenceInterventionPolicy, context: TenantContext
    ) -> None: ...

    def generate(
        self,
        original_evidence: Any,
        descriptor: ToolEvidenceDescriptor,
        policy: EvidenceInterventionPolicy,
        strategy: ControlledEvidenceStrategy,
        seed: int,
        context: TenantContext,
    ) -> tuple[Any, CounterfactualEvidence]: ...

    def validate_semantics(
        self,
        counterfactual_evidence: Any,
        policy: EvidenceInterventionPolicy,
        context: TenantContext,
    ) -> None: ...


class EvidenceValueResolver(Protocol):
    """Resolves durable evidence references under the caller's tenant context."""

    def resolve(self, reference: str, context: TenantContext) -> Any: ...

    def digest(self, value: Any) -> str: ...

    def put_counterfactual(
        self, value: Any, context: TenantContext, provenance: Mapping[str, Any]
    ) -> str: ...


__all__ = ["EvidenceInterventionProvider", "EvidenceValueResolver"]
