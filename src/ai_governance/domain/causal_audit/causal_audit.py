"""Immutable, provider-neutral causal audit domain contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any


class CausalAuditStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CausalAuditEligibilityCode(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_REPLAYABLE = "NOT_REPLAYABLE"
    MISSING_TOOL_EVIDENCE = "MISSING_TOOL_EVIDENCE"
    MISSING_SCORER = "MISSING_SCORER"
    UNSUPPORTED_TOOL = "UNSUPPORTED_TOOL"
    UNSUPPORTED_PROVIDER = "UNSUPPORTED_PROVIDER"
    INCOMPLETE_EXECUTION = "INCOMPLETE_EXECUTION"
    INTERVENTION_POLICY_NOT_CONFIGURED = "INTERVENTION_POLICY_NOT_CONFIGURED"
    INTERVENTION_POLICY_INACTIVE = "INTERVENTION_POLICY_INACTIVE"
    AMBIGUOUS_INTERVENTION_POLICY = "AMBIGUOUS_INTERVENTION_POLICY"
    INTERVENTION_PROVIDER_NOT_AVAILABLE = "INTERVENTION_PROVIDER_NOT_AVAILABLE"
    EVIDENCE_SCHEMA_UNAVAILABLE = "EVIDENCE_SCHEMA_UNAVAILABLE"
    UNSUPPORTED_EVIDENCE_TYPE = "UNSUPPORTED_EVIDENCE_TYPE"
    UNSUPPORTED_INTERVENTION = "UNSUPPORTED_INTERVENTION"


class EvidenceInterventionStrategy(str, Enum):
    NULLIFY = "NULLIFY"
    REPLACE = "REPLACE"
    PERTURB = "PERTURB"


class CausalAuditClassification(str, Enum):
    """Product vocabulary for evidence influence and tool-use behaviour."""

    NO_TOOL_EVIDENCE = "NO_TOOL_EVIDENCE"
    EVIDENCE_IGNORED = "EVIDENCE_IGNORED"
    OVER_EXTENDED = "OVER_EXTENDED"
    EVIDENCE_ALIGNED = "EVIDENCE_ALIGNED"


@dataclass(frozen=True)
class CausalAuditEligibility:
    code: CausalAuditEligibilityCode
    reason: str
    auditable_tool_call_count: int = 0


@dataclass(frozen=True)
class InterventionConfiguration:
    strategy: EvidenceInterventionStrategy
    counterfactual_samples: int
    strategy_version: str = "v1"
    seed: int | None = None
    configuration: Mapping[str, Any] = field(default_factory=dict)
    intervention_policy_id: str | None = None
    intervention_policy_version: int | None = None

    def __post_init__(self) -> None:
        if self.counterfactual_samples < 1:
            raise ValueError("counterfactual_samples must be at least one.")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty.")
        if (
            self.intervention_policy_id is not None
            and not self.intervention_policy_id.strip()
        ):
            raise ValueError("intervention_policy_id must not be blank.")
        if (
            self.intervention_policy_version is not None
            and self.intervention_policy_version < 1
        ):
            raise ValueError("intervention_policy_version must be positive.")
        if (self.intervention_policy_id is None) != (
            self.intervention_policy_version is None
        ):
            raise ValueError(
                "intervention policy ID and version must be supplied together."
            )
        object.__setattr__(
            self, "configuration", MappingProxyType(dict(self.configuration))
        )


@dataclass(frozen=True)
class OutcomeScore:
    value: float
    method: str
    provider: str
    evaluator_version: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not self.method.strip()
            or not self.provider.strip()
            or not self.evaluator_version.strip()
        ):
            raise ValueError(
                "OutcomeScore method, provider, and evaluator_version are required."
            )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class CounterfactualReplayLineage:
    """One complete, successful counterfactual replay/evaluator evidence chain."""

    replay_id: str
    replay_execution_id: str
    replay_status: str
    policy_id: str
    policy_version: int
    provider_id: str
    provider_version: str
    original_evidence_digest: str
    counterfactual_evidence_reference: str
    counterfactual_evidence_digest: str
    intervention_digest: str
    evaluator_score: OutcomeScore

    def __post_init__(self) -> None:
        for name, value in (
            ("replay_id", self.replay_id),
            ("replay_execution_id", self.replay_execution_id),
            ("policy_id", self.policy_id),
            ("provider_id", self.provider_id),
            ("provider_version", self.provider_version),
            ("original_evidence_digest", self.original_evidence_digest),
            ("counterfactual_evidence_reference", self.counterfactual_evidence_reference),
            ("counterfactual_evidence_digest", self.counterfactual_evidence_digest),
            ("intervention_digest", self.intervention_digest),
        ):
            if not value.strip():
                raise ValueError(f"Counterfactual replay lineage {name} is required.")
        if self.policy_version < 1:
            raise ValueError("Counterfactual replay lineage policy version is required.")
        if self.replay_status not in {
            "EXECUTION_COMPLETED",
            "EVALUATING",
            "COMPARING",
            "COMPLETED",
        }:
            raise ValueError(
                "Counterfactual replay lineage requires a successful replay status."
            )


@dataclass(frozen=True)
class ToolEvidenceInfluence:
    tool_call_id: str
    tool_name: str
    position: int
    intervention: InterventionConfiguration
    counterfactual_count: int
    baseline_score: OutcomeScore
    counterfactual_score: OutcomeScore
    influence_score: float
    useful: bool
    harmful: bool
    post_saturation: bool
    counterfactual_replay_ids: tuple[str, ...] = ()
    counterfactual_execution_ids: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    counterfactual_lineage: tuple[CounterfactualReplayLineage, ...] = ()

    def __post_init__(self) -> None:
        if not self.tool_call_id.strip() or not self.tool_name.strip():
            raise ValueError("tool_call_id and tool_name are required.")
        if self.position < 0 or self.counterfactual_count < 0:
            raise ValueError("position and counterfactual_count must be non-negative.")
        if self.harmful and self.useful:
            raise ValueError("A tool call cannot be both useful and harmful.")
        if self.counterfactual_count and (
            len(self.counterfactual_replay_ids) != self.counterfactual_count
            or len(self.counterfactual_execution_ids) != self.counterfactual_count
        ):
            raise ValueError(
                "Counterfactual influence requires one Replay and execution lineage ID per sample."
            )
        if not self.counterfactual_count and (
            self.counterfactual_replay_ids or self.counterfactual_execution_ids
        ):
            raise ValueError("Counterfactual lineage requires counterfactual samples.")
        if self.counterfactual_count and (
            len(self.counterfactual_lineage) != self.counterfactual_count
        ):
            raise ValueError(
                "Evidence influence requires complete counterfactual lineage per sample."
            )
        if not self.counterfactual_count and self.counterfactual_lineage:
            raise ValueError("Counterfactual provenance requires counterfactual samples.")
        if self.counterfactual_count:
            lineage_replay_ids = tuple(item.replay_id for item in self.counterfactual_lineage)
            lineage_execution_ids = tuple(
                item.replay_execution_id for item in self.counterfactual_lineage
            )
            if (
                lineage_replay_ids != tuple(self.counterfactual_replay_ids)
                or lineage_execution_ids != tuple(self.counterfactual_execution_ids)
            ):
                raise ValueError(
                    "Counterfactual replay lineage must match the recorded Replay IDs."
                )
            if self.intervention.intervention_policy_id is not None:
                for lineage in self.counterfactual_lineage:
                    if (
                        lineage.policy_id != self.intervention.intervention_policy_id
                        or lineage.policy_version
                        != self.intervention.intervention_policy_version
                    ):
                        raise ValueError(
                            "Evidence influence lineage must match the governed policy version."
                        )
        object.__setattr__(
            self, "counterfactual_replay_ids", tuple(self.counterfactual_replay_ids)
        )
        object.__setattr__(
            self,
            "counterfactual_execution_ids",
            tuple(self.counterfactual_execution_ids),
        )
        object.__setattr__(self, "evidence_references", tuple(self.evidence_references))
        object.__setattr__(
            self, "counterfactual_lineage", tuple(self.counterfactual_lineage)
        )
        object.__setattr__(
            self, "diagnostics", MappingProxyType(dict(self.diagnostics))
        )


@dataclass(frozen=True)
class CausalAudit:
    audit_id: str
    organization_id: str
    project_id: str | None
    execution_id: str
    agent_id: str
    status: CausalAuditStatus
    methodology_version: str
    evaluator_ref: str
    intervention: InterventionConfiguration
    request_fingerprint: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    classification: CausalAuditClassification | None = None
    tool_call_results: tuple[ToolEvidenceInfluence, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    version: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("audit_id", self.audit_id),
            ("organization_id", self.organization_id),
            ("execution_id", self.execution_id),
            ("agent_id", self.agent_id),
            ("methodology_version", self.methodology_version),
            ("evaluator_ref", self.evaluator_ref),
            ("request_fingerprint", self.request_fingerprint),
            ("created_by", self.created_by),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty.")
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("project_id must not be blank.")
        if self.updated_at < self.created_at or self.version < 0:
            raise ValueError("Invalid audit timestamps or version.")
        if self.status is CausalAuditStatus.SUCCEEDED and (
            self.completed_at is None or self.classification is None
        ):
            raise ValueError(
                "Succeeded audits require completed_at and classification."
            )
        if self.status is CausalAuditStatus.FAILED and not self.failure_code:
            raise ValueError("Failed audits require a failure_code.")
        if (
            self.status
            in {
                CausalAuditStatus.SUCCEEDED,
                CausalAuditStatus.FAILED,
                CausalAuditStatus.CANCELLED,
            }
            and self.completed_at is None
        ):
            raise ValueError("Terminal audits require completed_at.")
        object.__setattr__(self, "tool_call_results", tuple(self.tool_call_results))
        object.__setattr__(
            self, "diagnostics", MappingProxyType(dict(self.diagnostics))
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            CausalAuditStatus.SUCCEEDED,
            CausalAuditStatus.FAILED,
            CausalAuditStatus.CANCELLED,
        }

    def mark_running(self, now: datetime) -> CausalAudit:
        if self.status is not CausalAuditStatus.QUEUED:
            raise ValueError(f"Cannot start an audit in {self.status.value}.")
        return replace(
            self,
            status=CausalAuditStatus.RUNNING,
            started_at=now,
            updated_at=now,
            version=self.version + 1,
        )

    def mark_succeeded(
        self,
        classification: CausalAuditClassification,
        results: tuple[ToolEvidenceInfluence, ...],
        diagnostics: Mapping[str, Any],
        now: datetime,
    ) -> CausalAudit:
        if self.status is not CausalAuditStatus.RUNNING:
            raise ValueError(f"Cannot complete an audit in {self.status.value}.")
        return replace(
            self,
            status=CausalAuditStatus.SUCCEEDED,
            classification=classification,
            tool_call_results=results,
            diagnostics=diagnostics,
            completed_at=now,
            updated_at=now,
            version=self.version + 1,
        )

    def mark_waiting_for_replays(
        self, diagnostics: Mapping[str, Any], now: datetime
    ) -> CausalAudit:
        if self.status is not CausalAuditStatus.RUNNING:
            raise ValueError(
                f"Cannot record replay work for an audit in {self.status.value}."
            )
        return replace(
            self,
            diagnostics=MappingProxyType(dict(diagnostics)),
            updated_at=now,
            version=self.version + 1,
        )

    def mark_failed(self, code: str, reason: str, now: datetime) -> CausalAudit:
        if self.is_terminal:
            raise ValueError("Terminal causal audits are immutable.")
        return replace(
            self,
            status=CausalAuditStatus.FAILED,
            failure_code=code,
            failure_reason=reason,
            completed_at=now,
            updated_at=now,
            version=self.version + 1,
        )

    def mark_cancelled(self, now: datetime) -> CausalAudit:
        if self.is_terminal:
            raise ValueError("Terminal causal audits are immutable.")
        return replace(
            self,
            status=CausalAuditStatus.CANCELLED,
            completed_at=now,
            updated_at=now,
            version=self.version + 1,
        )
