"""Advisor discovery and bounded evidence orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from ai_governance.spi.intelligence import Advisor, AdvisorDescriptor, AdvisorFinding, AdvisorRequest, Planner, ReasoningPlan


class AdvisorRegistrationError(ValueError):
    """Raised when advisor identity or a plan cannot be resolved safely."""


class AdvisorRegistry:
    """Discover advisors by stable ID and reject ambiguous registrations."""

    def __init__(self, advisors: tuple[Advisor, ...] = ()) -> None:
        self._advisors: dict[str, Advisor] = {}
        for advisor in advisors:
            self.register(advisor)

    def register(self, advisor: Advisor) -> None:
        """Register one advisor once; replacement is intentionally unsupported."""
        advisor_id = advisor.descriptor.advisor_id
        if advisor_id in self._advisors:
            raise AdvisorRegistrationError(f"Advisor '{advisor_id}' is already registered.")
        self._advisors[advisor_id] = advisor

    def descriptors(self) -> tuple[AdvisorDescriptor, ...]:
        """Return stable advisor metadata in deterministic ID order."""
        return tuple(self._advisors[advisor_id].descriptor for advisor_id in sorted(self._advisors))

    def resolve(self, advisor_id: str) -> Advisor:
        """Resolve one advisor or fail before executing a partial plan."""
        try:
            return self._advisors[advisor_id]
        except KeyError as exc:
            raise AdvisorRegistrationError(f"Advisor '{advisor_id}' is not registered.") from exc


@dataclass(frozen=True)
class IntelligenceResult:
    """A stateless plan together with only its selected advisor evidence."""

    plan: ReasoningPlan
    findings: tuple[AdvisorFinding, ...]

    def as_dict(self) -> dict[str, object]:
        return {**self.plan.as_dict(), "findings": [finding.as_dict() for finding in self.findings]}


class IntelligenceService:
    """Plan before execution; no LLM, repository, or conversation state lives here."""

    def __init__(self, registry: AdvisorRegistry, planner: Planner) -> None:
        self._registry = registry
        self._planner = planner

    def plan(self, request: AdvisorRequest) -> ReasoningPlan:
        """Choose advisors from discoverable descriptors without running them."""
        return self._planner.plan(request, self._registry.descriptors())

    def advisor_descriptors(self) -> tuple[AdvisorDescriptor, ...]:
        """Expose discoverable advisor metadata without planning or execution."""
        return self._registry.descriptors()

    def collect(self, request: AdvisorRequest, plan: ReasoningPlan | None = None) -> IntelligenceResult:
        """Run exactly the advisors chosen by the supplied deterministic plan."""
        resolved_plan = plan or self.plan(request)
        findings = tuple(self._registry.resolve(advisor_id).analyze(request) for advisor_id in resolved_plan.selected_advisor_ids)
        return IntelligenceResult(plan=resolved_plan, findings=findings)


__all__ = ["AdvisorRegistrationError", "AdvisorRegistry", "IntelligenceResult", "IntelligenceService"]
