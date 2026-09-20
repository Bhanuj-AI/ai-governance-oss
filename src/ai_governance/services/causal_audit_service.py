"""Application service and job handler for execution-level causal audits."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from ai_governance.domain.agent_execution import AgentExecutionStatus, EventType
from ai_governance.domain.causal_audit import (
    CausalAudit,
    CausalAuditClassification,
    CausalAuditEligibility,
    CausalAuditEligibilityCode,
    CausalAuditStatus,
    CounterfactualReplayLineage,
    EvidenceInterventionStrategy,
    InterventionConfiguration,
    OutcomeScore,
    ToolEvidenceInfluence,
)
from ai_governance.domain.jobs import (
    Job,
    JobExecutionContext,
    JobResult,
    JobStatus,
    JobSubmission,
    JobType,
)
from ai_governance.domain.replay import (
    ControlledEvidenceIntervention,
    ControlledEvidenceStrategy,
    ReplayStatus,
)
from ai_governance.domain.runtime_findings.finding import (
    EvidenceReference,
    FindingLifecycle,
    FindingSeverity,
    MetricSnapshot,
    RuntimeFinding,
)
from ai_governance.repositories.causal_audit_repository import CausalAuditListFilters
from ai_governance.spi.causal_audit import OutcomeScorer
from ai_governance.tenancy.domain import TenantContext


class CausalAuditNotFound(ValueError):
    pass


class CausalAuditNotEligible(ValueError):
    pass


class EvaluatorUnavailable(ValueError):
    pass


class InsufficientCounterfactualEvidence(ValueError):
    pass


class InterventionUnavailable(ValueError):
    """A governed policy was requested but no authorized generator is wired."""

    code = "INTERVENTION_PROVIDER_NOT_AVAILABLE"


@dataclass(frozen=True)
class CausalAuditSettings:
    influence_threshold: float = 0.01
    saturation_threshold: float = 0.95
    default_counterfactual_samples: int = 3
    max_counterfactual_samples: int = 10
    max_tool_calls: int = 20

    @classmethod
    def from_configuration(
        cls, configuration_service, context: TenantContext
    ) -> CausalAuditSettings:
        from ai_governance.settings_control.operational import setting_context

        scoped = setting_context(context)
        return cls(
            influence_threshold=float(
                configuration_service.get("causal_audit.influence_threshold", scoped)
            ),
            saturation_threshold=float(
                configuration_service.get("causal_audit.saturation_threshold", scoped)
            ),
            default_counterfactual_samples=int(
                configuration_service.get(
                    "causal_audit.default_counterfactual_samples", scoped
                )
            ),
            max_counterfactual_samples=int(
                configuration_service.get(
                    "causal_audit.max_counterfactual_samples", scoped
                )
            ),
            max_tool_calls=int(
                configuration_service.get("causal_audit.max_tool_calls", scoped)
            ),
        )


class RecordedOutcomeScorer:
    """Safe built-in scorer for runtimes that persist numeric outcome artifacts.

    It consumes only a bounded score recorded by the external runtime; it never
    reconstructs prompts, calls tools, or accesses raw evidence. Production
    installations can register an OutcomeScorer backed by their isolated replay.
    """

    evaluator_ref = "recorded-outcome/v1"

    def score_baseline(self, execution_id: str, event) -> OutcomeScore:
        value = event.attributes.get("score")
        if not isinstance(value, (int, float)):
            raise EvaluatorUnavailable(
                "The selected evaluator has no recorded baseline score."
            )
        return OutcomeScore(
            float(value),
            "recorded_numeric",
            "runtime",
            "v1",
            {"execution_id": execution_id},
        )

    def score_counterfactual(
        self,
        execution_id: str,
        tool_event,
        sample_index: int,
        intervention: InterventionConfiguration,
    ) -> OutcomeScore:
        raise EvaluatorUnavailable(
            "Counterfactual outcomes must be produced by a controlled Replay."
        )


class CausalAuditService:
    METHODOLOGY_VERSION = "causal-audit/v1"

    def __init__(
        self,
        audit_repository,
        execution_repository,
        event_repository,
        job_service=None,
        scorers: tuple[OutcomeScorer, ...] = (RecordedOutcomeScorer(),),
        settings: CausalAuditSettings | None = None,
        clock: Callable[[], datetime] | None = None,
        id_generator: Callable[[], str] | None = None,
        finding_repository=None,
        replay_application_service=None,
        replay_repository=None,
        replay_source_bridge=None,
        replay_execution_store=None,
        counterfactual_generator=None,
        intervention_policy_service=None,
    ) -> None:
        self._audits = audit_repository
        self._executions = execution_repository
        self._events = event_repository
        self._jobs = job_service
        self._scorers = {scorer.evaluator_ref: scorer for scorer in scorers}
        self._settings = settings or CausalAuditSettings()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ids = id_generator or (lambda: uuid4().hex)
        self._finding_repository = finding_repository
        self._replay_application = replay_application_service
        self._replays = replay_repository
        self._replay_source_bridge = replay_source_bridge
        self._replay_execution_store = replay_execution_store
        self._counterfactual_generator = counterfactual_generator
        self._intervention_policies = intervention_policy_service

    def eligibility(
        self,
        execution_id: str,
        context: TenantContext,
        evaluator_ref: str = RecordedOutcomeScorer.evaluator_ref,
        intervention_strategy: EvidenceInterventionStrategy = EvidenceInterventionStrategy.REPLACE,
        intervention_policy_id: str | None = None,
        intervention_policy_version: int | None = None,
    ) -> CausalAuditEligibility:
        execution = self._executions.get(
            execution_id, context.organization_id, context.project_id
        )
        if execution is None:
            return CausalAuditEligibility(
                CausalAuditEligibilityCode.NOT_REPLAYABLE,
                "Execution was not found in the current tenant scope.",
            )
        if execution.status is not AgentExecutionStatus.SUCCEEDED:
            return CausalAuditEligibility(
                CausalAuditEligibilityCode.INCOMPLETE_EXECUTION,
                "Only successfully completed executions can be causally audited.",
            )
        if evaluator_ref not in self._scorers:
            return CausalAuditEligibility(
                CausalAuditEligibilityCode.MISSING_SCORER,
                "The requested outcome scorer is unavailable.",
            )
        events = self._events.list_by_execution(
            execution_id, context.organization_id, context.project_id
        )
        if not any(
            event.event_type is EventType.EVALUATION
            and isinstance(event.attributes.get("score"), (int, float))
            for event in events
        ):
            return CausalAuditEligibility(
                CausalAuditEligibilityCode.MISSING_SCORER,
                "Execution has no durable outcome score for the selected evaluator.",
            )
        calls = [event for event in events if event.event_type is EventType.TOOL_CALL]
        if len(calls) > self._settings.max_tool_calls:
            return CausalAuditEligibility(
                CausalAuditEligibilityCode.UNSUPPORTED_TOOL,
                "Execution exceeds the configured causal-audit tool-call limit.",
                len(calls),
            )
        if calls:
            if (
                self._counterfactual_generator is None
                or self._intervention_policies is None
            ):
                return CausalAuditEligibility(
                    CausalAuditEligibilityCode.INTERVENTION_PROVIDER_NOT_AVAILABLE,
                    "No authorized evidence intervention provider is configured.",
                    len(calls),
                )
            if not self._controlled_replay_available(
                execution, events, context, intervention_strategy
            ):
                return CausalAuditEligibility(
                    CausalAuditEligibilityCode.UNSUPPORTED_TOOL,
                    "Execution has no supported, isolated controlled Replay capability.",
                    len(calls),
                )
            try:
                audited_calls = self._audited_tool_calls(
                    calls,
                    ControlledEvidenceStrategy(intervention_strategy.value),
                    intervention_policy_id,
                    intervention_policy_version,
                    context,
                )
            except Exception as error:  # noqa: BLE001 - report eligibility without leaking a provider failure.
                return CausalAuditEligibility(
                    _eligibility_code(error), str(error), len(calls)
                )
            if not audited_calls:
                return CausalAuditEligibility(
                    CausalAuditEligibilityCode.UNSUPPORTED_INTERVENTION,
                    "The selected intervention policy does not authorize any tool calls in this execution.",
                    len(calls),
                )
        return CausalAuditEligibility(
            CausalAuditEligibilityCode.ELIGIBLE,
            "Execution has bounded evidence references and isolated replay capability.",
            len(calls),
        )

    def start(
        self,
        execution_id: str,
        evaluator_ref: str,
        intervention: InterventionConfiguration,
        context: TenantContext,
    ) -> CausalAudit:
        eligibility = self.eligibility(
            execution_id,
            context,
            evaluator_ref,
            intervention.strategy,
            intervention.intervention_policy_id,
            intervention.intervention_policy_version,
        )
        if eligibility.code is not CausalAuditEligibilityCode.ELIGIBLE:
            raise CausalAuditNotEligible(
                f"{eligibility.code.value}: {eligibility.reason}"
            )
        if (
            intervention.counterfactual_samples
            > self._settings.max_counterfactual_samples
        ):
            raise ValueError("counterfactual_samples exceeds the configured maximum.")
        execution = self._executions.get(
            execution_id, context.organization_id, context.project_id
        )
        assert execution is not None
        fingerprint = _fingerprint(
            context, execution_id, self.METHODOLOGY_VERSION, evaluator_ref, intervention
        )
        existing = self._audits.find_by_fingerprint(
            fingerprint, context.organization_id, context.project_id
        )
        if existing is not None:
            return existing
        now = self._clock()
        audit = CausalAudit(
            self._ids(),
            context.organization_id,
            context.project_id,
            execution_id,
            execution.agent_id,
            CausalAuditStatus.QUEUED,
            self.METHODOLOGY_VERSION,
            evaluator_ref,
            intervention,
            fingerprint,
            context.actor_id,
            now,
            now,
        )
        self._audits.save(audit)
        if self._jobs is not None:
            self._jobs.submit(
                JobSubmission(
                    JobType.CAUSAL_AUDIT,
                    {"audit_id": audit.audit_id},
                    f"causal-audit:{fingerprint}",
                    context.actor_id,
                    execution_context=JobExecutionContext(
                        context.organization_id,
                        context.project_id or "",
                        context.actor_id,
                        context.request_id,
                        context.correlation_id,
                    ),
                )
            )
            # Job is deliberately only a reference: audit state remains authoritative.
            return audit
        return audit

    def get(self, audit_id: str, context: TenantContext) -> CausalAudit:
        audit = self._audits.get(audit_id, context.organization_id, context.project_id)
        if audit is None:
            raise CausalAuditNotFound(f"Causal audit '{audit_id}' was not found.")
        return audit

    def list(
        self,
        context: TenantContext,
        filters: CausalAuditListFilters,
        execution_id: str | None = None,
    ) -> list[CausalAudit]:
        return self._audits.list(
            filters, context.organization_id, context.project_id, execution_id
        )

    def execute(self, audit_id: str, context: TenantContext) -> CausalAudit:
        audit = self.get(audit_id, context)
        if audit.status is CausalAuditStatus.SUCCEEDED:
            return audit
        if audit.status is CausalAuditStatus.CANCELLED:
            return audit
        if audit.status is CausalAuditStatus.QUEUED:
            audit = self._audits.save(
                audit.mark_running(self._clock()), expected_version=audit.version
            )
        try:
            eligibility = self.eligibility(
                audit.execution_id,
                context,
                audit.evaluator_ref,
                audit.intervention.strategy,
                audit.intervention.intervention_policy_id,
                audit.intervention.intervention_policy_version,
            )
            if eligibility.code is not CausalAuditEligibilityCode.ELIGIBLE:
                raise CausalAuditNotEligible(
                    f"{eligibility.code.value}: {eligibility.reason}"
                )
            events = self._events.list_by_execution(
                audit.execution_id, context.organization_id, context.project_id
            )
            scorer = self._scorers[audit.evaluator_ref]
            baseline_event = next(
                event
                for event in reversed(events)
                if event.event_type is EventType.EVALUATION
                and isinstance(event.attributes.get("score"), (int, float))
            )
            baseline = scorer.score_baseline(audit.execution_id, baseline_event)
            all_calls = [
                event for event in events if event.event_type is EventType.TOOL_CALL
            ]
            calls = self._audited_tool_calls(
                all_calls,
                ControlledEvidenceStrategy(audit.intervention.strategy.value),
                audit.intervention.intervention_policy_id,
                audit.intervention.intervention_policy_version,
                context,
            )
            planned = _planned_replays(audit)
            if calls and not planned:
                audit = self._queue_controlled_replays(audit, events, calls, context)
                return audit
            if calls and not self._controlled_replays_completed(planned, context):
                return audit
            results: list[ToolEvidenceInfluence] = []
            saturated = baseline.value >= self._settings.saturation_threshold
            for position, event in enumerate(calls):
                samples, replay_ids, execution_ids, replay_lineage = self._replay_outcomes(
                    event.event_id, planned, context
                )
                if not samples:
                    raise InsufficientCounterfactualEvidence(
                        "No valid counterfactual Replay outcome was available."
                    )
                aggregate = sum(sample.value for sample in samples) / len(samples)
                counterfactual = OutcomeScore(
                    aggregate,
                    samples[0].method,
                    samples[0].provider,
                    samples[0].evaluator_version,
                    {"aggregation": "mean", "sample_count": len(samples)},
                )
                influence = baseline.value - aggregate
                tool_name = str(
                    event.attributes.get("tool") or event.actor_id or "tool"
                )
                useful = influence >= self._settings.influence_threshold
                harmful = (
                    not useful and influence <= -self._settings.influence_threshold
                )
                results.append(
                    ToolEvidenceInfluence(
                        event.event_id,
                        tool_name,
                        position,
                        audit.intervention,
                        len(samples),
                        baseline,
                        counterfactual,
                        influence,
                        useful,
                        harmful,
                        saturated and position > 0,
                        replay_ids,
                        execution_ids,
                        tuple(event.evidence_references),
                        {
                            "counterfactual_aggregation": "mean",
                            "replay_count": len(replay_ids),
                            "intervention_provenance": _planned_provenance(
                                event.event_id, planned
                            ),
                        },
                        replay_lineage,
                    )
                )
                saturated = saturated or useful
            classification, reason = _classify(results, len(calls), self._settings)
            post_saturation = [item for item in results if item.post_saturation]
            material = next((item for item in results if item.useful), None)
            diagnostics = {
                **dict(audit.diagnostics),
                "classification_reason": reason,
                "thresholds": {
                    "influence_threshold": self._settings.influence_threshold,
                    "saturation_threshold": self._settings.saturation_threshold,
                    "max_tool_calls": self._settings.max_tool_calls,
                },
                "result_digest": _result_digest(baseline, results),
                "baseline_score": baseline.value,
                "tool_use_analysis": {
                    "saturation_reached_after_tool_call_id": material.tool_call_id
                    if post_saturation and material
                    else None,
                    "post_saturation_tool_call_ids": [
                        item.tool_call_id for item in post_saturation
                    ],
                },
            }
            completed = self._audits.save(
                audit.mark_succeeded(
                    classification, tuple(results), diagnostics, self._clock()
                ),
                expected_version=audit.version,
            )
            self._emit_findings(completed)
            return completed
        except Exception as error:  # noqa: BLE001 - record a deterministic audit failure.
            current = self.get(audit_id, context)
            if current.is_terminal:
                return current
            code = getattr(
                error,
                "code",
                "INSUFFICIENT_COUNTERFACTUAL_EVIDENCE"
                if isinstance(error, InsufficientCounterfactualEvidence)
                else type(error).__name__.upper(),
            )
            return self._audits.save(
                current.mark_failed(code, str(error), self._clock()),
                expected_version=current.version,
            )

    def _audited_tool_calls(
        self,
        calls,
        strategy: ControlledEvidenceStrategy,
        intervention_policy_id: str | None,
        intervention_policy_version: int | None,
        context: TenantContext,
    ):
        """Return only calls governed by an explicitly selected policy."""
        assert self._counterfactual_generator is not None
        selected = calls
        if intervention_policy_id is not None:
            if intervention_policy_version is None:
                raise ValueError("An explicit intervention policy requires a version.")
            policy = self._intervention_policies.get(
                intervention_policy_id, intervention_policy_version, context
            )
            selected = [
                event for event in calls if _policy_matches_tool_evidence(policy, event)
            ]
        for event in selected:
            self._counterfactual_generator.validate(
                event,
                strategy,
                intervention_policy_id,
                intervention_policy_version,
                context,
            )
        return selected

    def _controlled_replay_available(
        self,
        execution,
        events,
        context: TenantContext,
        intervention_strategy: EvidenceInterventionStrategy,
    ) -> bool:
        if (
            self._replay_application is None
            or self._replays is None
            or self._replay_source_bridge is None
            or self._replay_execution_store is None
        ):
            return False
        try:
            capability, _ = self._replay_source_bridge.validate(
                execution, events, context
            )
            return (
                ControlledEvidenceStrategy(intervention_strategy.value)
                in capability.supported_interventions
            )
        except (TypeError, ValueError):
            return False

    def _queue_controlled_replays(self, audit, events, calls, context: TenantContext):
        if self._counterfactual_generator is None:
            raise InterventionUnavailable(
                "INTERVENTION_PROVIDER_NOT_AVAILABLE: no authorized evidence "
                "resolver is configured for this runtime adapter."
            )
        execution = self._executions.get(
            audit.execution_id, context.organization_id, context.project_id
        )
        if execution is None:
            raise CausalAuditNotEligible(
                "Execution was not found in the current tenant scope."
            )
        prepared = self._replay_source_bridge.prepare(execution, events, context)
        strategy = ControlledEvidenceStrategy(audit.intervention.strategy.value)
        if strategy not in prepared.capability.supported_interventions:
            raise CausalAuditNotEligible(
                f"{audit.intervention.strategy.value} is unsupported by the execution Replay capability."
            )
        planned: list[dict[str, object]] = []
        for event in calls:
            generated_digests: set[str] = set()
            for sample_index in range(audit.intervention.counterfactual_samples):
                source_reference = event.evidence_references[0]
                seed = _intervention_seed(audit, event.event_id, sample_index)
                generated = (
                    self._counterfactual_generator.generate(
                        event,
                        strategy,
                        audit.intervention.intervention_policy_id,
                        audit.intervention.intervention_policy_version,
                        seed,
                        context,
                    )
                    if self._counterfactual_generator is not None
                    else None
                )
                if generated.counterfactual_evidence_digest in generated_digests:
                    continue
                generated_digests.add(generated.counterfactual_evidence_digest)
                intervention = ControlledEvidenceIntervention(
                    strategy=strategy,
                    strategy_version=audit.intervention.strategy_version,
                    source_evidence_reference=source_reference,
                    target_event_id=event.event_id,
                    counterfactual_evidence_reference=(
                        generated.counterfactual_evidence_ref
                    ),
                    seed=seed,
                    configuration={
                        **dict(audit.intervention.configuration),
                        "sample_index": sample_index,
                    },
                    policy_id=generated.policy_id if generated else None,
                    policy_version=generated.policy_version if generated else None,
                    provider_id=generated.provider_id if generated else None,
                    provider_version=generated.provider_version if generated else None,
                    original_evidence_digest=generated.original_evidence_digest
                    if generated
                    else None,
                    counterfactual_evidence_digest=generated.counterfactual_evidence_digest
                    if generated
                    else None,
                )
                replay = self._replay_application.create(
                    source_execution_id=prepared.source_execution.execution_id,
                    context=context,
                    idempotency_key=(
                        f"causal-audit:{audit.audit_id}:{event.event_id}:{sample_index}"
                    ),
                    metadata={
                        "causal_audit_id": audit.audit_id,
                        "tool_call_id": event.event_id,
                        "sample_index": sample_index,
                        "controlled_replay": True,
                        "intervention_policy_id": generated.policy_id
                        if generated
                        else None,
                        "intervention_policy_version": generated.policy_version
                        if generated
                        else None,
                    },
                    controlled_evidence_intervention=intervention,
                )
                queued = self._replay_application.submit(replay.replay_id, context)
                planned.append(
                    {
                        "tool_call_id": event.event_id,
                        "sample_index": sample_index,
                        "replay_id": queued.replay_id,
                        "policy_id": intervention.policy_id,
                        "policy_version": intervention.policy_version,
                        "provider_id": intervention.provider_id,
                        "provider_version": intervention.provider_version,
                        "original_evidence_digest": intervention.original_evidence_digest,
                        "counterfactual_evidence_reference": intervention.counterfactual_evidence_reference,
                        "counterfactual_evidence_digest": intervention.counterfactual_evidence_digest,
                        "intervention_digest": intervention.intervention_digest,
                    }
                )
        diagnostics = {
            **dict(audit.diagnostics),
            "counterfactual_replays": planned,
            "counterfactual_replay_source_execution_id": prepared.source_execution.execution_id,
            "controlled_replay_adapter": prepared.capability.adapter_id,
        }
        return self._audits.save(
            audit.mark_waiting_for_replays(diagnostics, self._clock()),
            expected_version=audit.version,
        )

    def _controlled_replays_completed(
        self, planned: list[dict[str, object]], context: TenantContext
    ) -> bool:
        for item in planned:
            replay = self._replays.get(
                str(item["replay_id"]),
                context.organization_id,
                context.project_id or "",
            )
            if replay is None:
                raise InsufficientCounterfactualEvidence(
                    "A controlled Replay disappeared."
                )
            if replay.status in {ReplayStatus.FAILED, ReplayStatus.CANCELLED}:
                raise InsufficientCounterfactualEvidence(
                    replay.failure.message
                    if replay.failure is not None
                    else "A controlled Replay did not complete."
                )
            if replay.status not in {
                ReplayStatus.EXECUTION_COMPLETED,
                ReplayStatus.EVALUATING,
                ReplayStatus.COMPARING,
                ReplayStatus.COMPLETED,
            }:
                return False
        return True

    def _replay_outcomes(
        self,
        tool_call_id: str,
        planned: list[dict[str, object]],
        context: TenantContext,
    ) -> tuple[
        list[OutcomeScore],
        tuple[str, ...],
        tuple[str, ...],
        tuple[CounterfactualReplayLineage, ...],
    ]:
        selected = [item for item in planned if item["tool_call_id"] == tool_call_id]
        selected.sort(key=lambda item: int(item["sample_index"]))
        scores: list[OutcomeScore] = []
        replay_ids: list[str] = []
        execution_ids: list[str] = []
        lineage: list[CounterfactualReplayLineage] = []
        for item in selected:
            replay_id = str(item["replay_id"])
            replay = self._replays.get(
                replay_id, context.organization_id, context.project_id or ""
            )
            if replay is None or replay.replay_execution_id is None:
                raise InsufficientCounterfactualEvidence(
                    "Controlled Replay execution lineage is unavailable."
                )
            output = self._replay_execution_store.get_execution(
                replay.replay_execution_id, context
            )
            value = (
                output.final_state.get("causal_audit_outcome_score")
                if output is not None
                else None
            )
            counterfactual_evidence_digest = (
                output.final_state.get("counterfactual_evidence_digest")
                if output is not None
                else None
            )
            if not isinstance(counterfactual_evidence_digest, str):
                counterfactual_evidence_digest = str(
                    item["counterfactual_evidence_digest"]
                )
            if not isinstance(value, (int, float)):
                raise InsufficientCounterfactualEvidence(
                    "Controlled Replay produced no evaluable outcome score."
                )
            replay_ids.append(replay_id)
            execution_ids.append(replay.replay_execution_id)
            scores.append(
                OutcomeScore(
                    float(value),
                    "controlled_replay_outcome",
                    "agent-runtime-replay",
                    "v1",
                    {
                        "replay_id": replay_id,
                        "replay_execution_id": replay.replay_execution_id,
                    },
                )
            )
            score = scores[-1]
            try:
                lineage.append(
                    CounterfactualReplayLineage(
                        replay_id=replay_id,
                        replay_execution_id=replay.replay_execution_id,
                        replay_status=replay.status.value,
                        policy_id=str(item["policy_id"]),
                        policy_version=int(item["policy_version"]),
                        provider_id=str(item["provider_id"]),
                        provider_version=str(item["provider_version"]),
                        original_evidence_digest=str(
                            item["original_evidence_digest"]
                        ),
                        counterfactual_evidence_reference=str(
                            item["counterfactual_evidence_reference"]
                        ),
                        counterfactual_evidence_digest=counterfactual_evidence_digest,
                        intervention_digest=str(item["intervention_digest"]),
                        evaluator_score=score,
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                raise InsufficientCounterfactualEvidence(
                    "Controlled Replay has incomplete governed intervention lineage."
                ) from error
        return scores, tuple(replay_ids), tuple(execution_ids), tuple(lineage)

    def _emit_findings(self, audit: CausalAudit) -> None:
        """Emit bounded lineage references; Findings never duplicate audit results."""
        if (
            self._finding_repository is None
            or audit.classification is CausalAuditClassification.EVIDENCE_ALIGNED
        ):
            return
        types: list[tuple[str, FindingSeverity, tuple[str, ...]]] = []
        if audit.classification is CausalAuditClassification.EVIDENCE_IGNORED:
            types.append(
                (
                    "EVIDENCE_IGNORED",
                    FindingSeverity.MEDIUM,
                    tuple(item.tool_call_id for item in audit.tool_call_results),
                )
            )
        if audit.classification is CausalAuditClassification.OVER_EXTENDED:
            types.append(
                (
                    "OVER_EXTENDED",
                    FindingSeverity.MEDIUM,
                    tuple(
                        item.tool_call_id
                        for item in audit.tool_call_results
                        if item.post_saturation
                    ),
                )
            )
        for item in audit.tool_call_results:
            if item.harmful:
                types.append(
                    ("HARMFUL_EVIDENCE", FindingSeverity.HIGH, (item.tool_call_id,))
                )
            elif not item.useful:
                types.append(
                    ("REDUNDANT_TOOL_CALL", FindingSeverity.LOW, (item.tool_call_id,))
                )
        for finding_type, severity, tool_call_ids in types:
            self._finding_repository.save(
                RuntimeFinding(
                    finding_id=f"causal-audit:{audit.audit_id}:{finding_type}:{'-'.join(tool_call_ids) or 'execution'}",
                    organization_id=audit.organization_id,
                    project_id=audit.project_id,
                    finding_type=finding_type,
                    subject_type="agent_execution",
                    subject_id=audit.execution_id,
                    severity=severity,
                    lifecycle=FindingLifecycle.CASE_REVIEW,
                    observation_count=max(1, len(tool_call_ids)),
                    observed_metrics=(
                        MetricSnapshot(
                            "max_evidence_influence",
                            max(
                                (
                                    item.influence_score
                                    for item in audit.tool_call_results
                                ),
                                default=0.0,
                            ),
                            len(audit.tool_call_results),
                        ),
                    ),
                    evidence_references=(
                        EvidenceReference("causal_audit_id", audit.audit_id),
                        EvidenceReference("execution_id", audit.execution_id),
                        EvidenceReference(
                            "methodology_version", audit.methodology_version
                        ),
                        *(
                            EvidenceReference("tool_call_id", identifier)
                            for identifier in tool_call_ids
                        ),
                    ),
                    related_execution_ids=(audit.execution_id,),
                    detector_id="causal_audit",
                    detector_version=audit.methodology_version,
                    first_detected_at=audit.completed_at,
                    last_detected_at=audit.completed_at,
                    created_at=audit.completed_at or self._clock(),
                    updated_at=audit.completed_at or self._clock(),
                )
            )


class CausalAuditJobHandler:
    def __init__(self, service: CausalAuditService) -> None:
        self._service = service

    def handle(self, job: Job) -> JobResult:
        if job.execution_context is None:
            return JobResult(
                job.job_id,
                JobStatus.FAILED,
                None,
                "Causal audit job is missing tenant context.",
            )
        scope = job.execution_context
        context = TenantContext(
            scope.organization_id,
            scope.project_id or None,
            scope.actor_id,
            scope.submitted_request_id,
            scope.correlation_id,
        )
        audit = self._service.execute(str(job.input_refs["audit_id"]), context)
        if audit.status is CausalAuditStatus.SUCCEEDED:
            return JobResult(
                job.job_id, JobStatus.SUCCEEDED, f"causal_audit:{audit.audit_id}", None
            )
        if audit.status is CausalAuditStatus.CANCELLED:
            return JobResult(
                job.job_id, JobStatus.CANCELLED, None, "Causal audit cancelled."
            )
        if audit.status is CausalAuditStatus.RUNNING:
            return JobResult(
                job.job_id,
                JobStatus.SUCCEEDED,
                f"causal_audit_pending:{audit.audit_id}",
                None,
            )
        return JobResult(
            job.job_id,
            JobStatus.FAILED,
            None,
            audit.failure_reason or "Causal audit failed.",
        )


def _classify(
    results: list[ToolEvidenceInfluence], call_count: int, settings: CausalAuditSettings
) -> tuple[CausalAuditClassification, str]:
    if call_count == 0:
        return (
            CausalAuditClassification.NO_TOOL_EVIDENCE,
            "No tool call was available for causal evidence analysis.",
        )
    material = [result for result in results if result.useful]
    if not material:
        return (
            CausalAuditClassification.EVIDENCE_IGNORED,
            "No returned tool evidence materially changed the evaluated outcome.",
        )
    budget_exhausted = call_count >= settings.max_tool_calls
    post_saturation = any(result.post_saturation for result in results)
    if post_saturation or budget_exhausted:
        why = (
            "The execution continued after useful evidence reached saturation."
            if post_saturation
            else "The execution exhausted the configured tool-call budget after useful evidence."
        )
        return CausalAuditClassification.OVER_EXTENDED, why
    return (
        CausalAuditClassification.EVIDENCE_ALIGNED,
        "Returned evidence materially changed the evaluated outcome and the execution stopped without post-saturation calls.",
    )


def _planned_replays(audit: CausalAudit) -> list[dict[str, object]]:
    raw = audit.diagnostics.get("counterfactual_replays", ())
    if not isinstance(raw, list):
        return []
    planned: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict) or not {
            "tool_call_id",
            "sample_index",
            "replay_id",
        }.issubset(item):
            raise InsufficientCounterfactualEvidence(
                "Causal Audit replay plan is malformed."
            )
        planned.append(dict(item))
    return planned


def _eligibility_code(error: Exception) -> CausalAuditEligibilityCode:
    code = getattr(error, "code", None)
    try:
        return CausalAuditEligibilityCode(code)
    except ValueError:
        return CausalAuditEligibilityCode.UNSUPPORTED_INTERVENTION


def _policy_matches_tool_evidence(policy, event) -> bool:
    """Whether an event's bounded descriptor identifies evidence governed by policy."""
    raw = event.attributes.get("causal_replay")
    descriptor = raw.get("evidence_descriptor") if isinstance(raw, Mapping) else None
    if not isinstance(descriptor, Mapping):
        return False
    tool_name = (
        descriptor.get("tool_name") or event.attributes.get("tool") or event.actor_id
    )
    return (
        tool_name == policy.tool_name
        and descriptor.get("schema_id") == policy.schema_id
        and descriptor.get("schema_version") == policy.schema_version
    )


def _planned_provenance(
    tool_call_id: str, planned: list[dict[str, object]]
) -> dict[str, object]:
    """Return durable intervention lineage only; never materialize evidence."""
    first = next(
        (item for item in planned if item["tool_call_id"] == tool_call_id), None
    )
    if first is None:
        return {}
    keys = (
        "policy_id",
        "policy_version",
        "provider_id",
        "provider_version",
        "original_evidence_digest",
        "counterfactual_evidence_reference",
        "counterfactual_evidence_digest",
        "intervention_digest",
    )
    return {key: first[key] for key in keys if first.get(key) is not None}


def _counterfactual_reference(
    source_reference: str, audit_id: str, tool_call_id: str, sample_index: int
) -> str:
    """Generate a deterministic opaque reference; never embed the evidence payload."""
    digest = sha256(
        f"{source_reference}|{audit_id}|{tool_call_id}|{sample_index}".encode()
    ).hexdigest()[:20]
    return f"counterfactual-evidence:{digest}"


def _intervention_seed(audit: CausalAudit, tool_call_id: str, sample_index: int) -> int:
    if audit.intervention.seed is not None:
        return audit.intervention.seed + sample_index
    value = "|".join(
        (
            audit.execution_id,
            tool_call_id,
            audit.intervention.strategy.value,
            str(sample_index),
            audit.methodology_version,
            audit.intervention.intervention_policy_id or "",
        )
    )
    return int(sha256(value.encode()).hexdigest()[:16], 16)


def _fingerprint(
    context: TenantContext,
    execution_id: str,
    methodology: str,
    evaluator_ref: str,
    intervention: InterventionConfiguration,
) -> str:
    payload = {
        "organization": context.organization_id,
        "project": context.project_id,
        "execution": execution_id,
        "methodology": methodology,
        "evaluator": evaluator_ref,
        "intervention": {
            "strategy": intervention.strategy.value,
            "version": intervention.strategy_version,
            "samples": intervention.counterfactual_samples,
            "seed": intervention.seed,
            "configuration": dict(intervention.configuration),
            "policy_id": intervention.intervention_policy_id,
            "policy_version": intervention.intervention_policy_version,
        },
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _result_digest(baseline: OutcomeScore, results: list[ToolEvidenceInfluence]) -> str:
    payload = {
        "baseline": baseline.value,
        "results": [
            {"tool_call_id": result.tool_call_id, "influence": result.influence_score}
            for result in results
        ],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
