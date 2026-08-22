from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any


class ReplayStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    EVALUATING = "EVALUATING"
    COMPARING = "COMPARING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class ReplayMode(str, Enum):
    FULL = "FULL"


class ReplayConfigurationSource(str, Enum):
    ORIGINAL = "ORIGINAL"


class ReplayFailureStage(str, Enum):
    SOURCE_RESOLUTION = "SOURCE_RESOLUTION"
    AUTHORIZATION = "AUTHORIZATION"
    VALIDATION = "VALIDATION"
    CONFIGURATION_RESOLUTION = "CONFIGURATION_RESOLUTION"
    PERSISTENCE = "PERSISTENCE"
    JOB_SUBMISSION = "JOB_SUBMISSION"
    SOURCE_RELOAD = "SOURCE_RELOAD"
    ADAPTER_RESOLUTION = "ADAPTER_RESOLUTION"
    RECONSTRUCTION = "RECONSTRUCTION"
    EXECUTION = "EXECUTION"
    EXECUTION_PERSISTENCE = "EXECUTION_PERSISTENCE"
    LINEAGE_PERSISTENCE = "LINEAGE_PERSISTENCE"
    CANCELLATION = "CANCELLATION"
    EVALUATION_SUBMISSION = "EVALUATION_SUBMISSION"
    EVALUATION = "EVALUATION"
    BASELINE_RESOLUTION = "BASELINE_RESOLUTION"
    COMPARISON = "COMPARISON"
    DRIFT_ANALYSIS = "DRIFT_ANALYSIS"
    RESULT_PERSISTENCE = "RESULT_PERSISTENCE"
    ONTOLOGY_SYNC = "ONTOLOGY_SYNC"


@dataclass(frozen=True)
class ReplayConfiguration:
    """Immutable, historically resolved evidence for a future replay."""

    workflow_id: str
    workflow_version: str
    execution_adapter: str
    input_snapshot_ref: str
    state_snapshot_ref: str
    artifact_refs: tuple[str, ...] = ()
    prompt_refs: tuple[str, ...] = ()
    model_refs: tuple[str, ...] = ()
    dataset_refs: tuple[str, ...] = ()
    policy_refs: tuple[str, ...] = ()
    runtime_parameters: Mapping[str, Any] = field(default_factory=dict)
    configuration_source: ReplayConfigurationSource = ReplayConfigurationSource.ORIGINAL
    resolved_at: datetime | None = None
    configuration_hash: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("workflow_id", self.workflow_id),
            ("workflow_version", self.workflow_version),
            ("execution_adapter", self.execution_adapter),
            ("input_snapshot_ref", self.input_snapshot_ref),
            ("state_snapshot_ref", self.state_snapshot_ref),
            ("configuration_hash", self.configuration_hash),
        ):
            if not value.strip():
                raise ValueError(f"Replay configuration {name} is required.")
        if self.configuration_source is not ReplayConfigurationSource.ORIGINAL:
            raise ValueError("Only ORIGINAL replay configuration is supported.")
        object.__setattr__(
            self,
            "runtime_parameters",
            MappingProxyType(dict(self.runtime_parameters)),
        )


@dataclass(frozen=True)
class ReplayFailure:
    code: str
    message: str
    stage: ReplayFailureStage
    details: Mapping[str, Any]
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            raise ValueError("Replay failure code and message are required.")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True)
class Replay:
    """A durable, governed request to reproduce a historical execution."""

    replay_id: str
    source_execution_id: str
    status: ReplayStatus
    mode: ReplayMode
    requested_by: str
    organization_id: str
    project_id: str
    request_id: str
    idempotency_key: str
    input_hash: str
    created_at: datetime
    updated_at: datetime
    correlation_id: str | None = None
    configuration: ReplayConfiguration | None = None
    archived_at: datetime | None = None
    failure: ReplayFailure | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: int = 0
    job_id: str | None = None
    replay_execution_id: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    execution_completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    cancelled_at: datetime | None = None
    attempt_count: int = 0
    evaluation_job_id: str | None = None
    baseline_evaluation_id: str | None = None
    replay_evaluation_id: str | None = None
    comparison_id: str | None = None
    drift_id: str | None = None
    result_id: str | None = None
    evaluation_started_at: datetime | None = None
    evaluation_completed_at: datetime | None = None
    comparison_started_at: datetime | None = None
    comparison_completed_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        replay_id: str,
        source_execution_id: str,
        mode: ReplayMode,
        requested_by: str,
        organization_id: str,
        project_id: str,
        request_id: str,
        correlation_id: str | None,
        idempotency_key: str,
        input_hash: str,
        metadata: Mapping[str, Any],
        now: datetime,
    ) -> Replay:
        if mode is not ReplayMode.FULL:
            raise ValueError("Only FULL replay mode is supported.")
        for name, value in (
            ("replay_id", replay_id),
            ("source_execution_id", source_execution_id),
            ("requested_by", requested_by),
            ("organization_id", organization_id),
            ("project_id", project_id),
            ("request_id", request_id),
            ("idempotency_key", idempotency_key),
            ("input_hash", input_hash),
        ):
            if not value.strip():
                raise ValueError(f"Replay {name} is required.")
        return cls(
            replay_id=replay_id,
            source_execution_id=source_execution_id,
            status=ReplayStatus.DRAFT,
            mode=mode,
            requested_by=requested_by,
            organization_id=organization_id,
            project_id=project_id,
            request_id=request_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            created_at=now,
            updated_at=now,
            metadata=MappingProxyType(dict(metadata)),
        )

    def mark_ready(self, configuration: ReplayConfiguration, now: datetime) -> Replay:
        self._require_status(ReplayStatus.DRAFT, "mark ready")
        if self.failure is not None:
            raise ValueError("A failed replay cannot become ready.")
        return replace(
            self,
            status=ReplayStatus.READY,
            configuration=configuration,
            updated_at=now,
        )

    def mark_failed(self, failure: ReplayFailure, now: datetime) -> Replay:
        self._require_status(ReplayStatus.DRAFT, "mark failed")
        return replace(
            self,
            status=ReplayStatus.FAILED,
            failure=failure,
            updated_at=now,
        )

    def archive(self, now: datetime) -> Replay:
        if self.status not in {
            ReplayStatus.READY,
            ReplayStatus.EXECUTION_COMPLETED,
            ReplayStatus.COMPLETED,
            ReplayStatus.FAILED,
            ReplayStatus.CANCELLED,
        }:
            raise ValueError(f"Cannot archive replay in {self.status.value} state.")
        return replace(
            self,
            status=ReplayStatus.ARCHIVED,
            archived_at=now,
            updated_at=now,
        )

    def _require_status(self, expected: ReplayStatus, operation: str) -> None:
        if self.status is not expected:
            raise ValueError(f"Cannot {operation} replay in {self.status.value} state.")

    def mark_queued(self, job_id: str, now: datetime) -> Replay:
        self._require_status(ReplayStatus.READY, "queue")
        if not job_id.strip():
            raise ValueError("Replay job ID is required.")
        if self.job_id is not None and self.job_id != job_id:
            raise ValueError("Replay job ID is immutable once assigned.")
        return replace(
            self,
            status=ReplayStatus.QUEUED,
            job_id=job_id,
            queued_at=now,
            updated_at=now,
        )

    def mark_running(self, attempt_count: int, now: datetime) -> Replay:
        self._require_status(ReplayStatus.QUEUED, "start")
        if attempt_count < 1:
            raise ValueError("Replay attempt count must be positive.")
        return replace(
            self,
            status=ReplayStatus.RUNNING,
            started_at=now,
            updated_at=now,
            attempt_count=attempt_count,
        )

    def reserve_replay_execution_id(
        self, replay_execution_id: str, now: datetime
    ) -> Replay:
        if self.status not in {ReplayStatus.QUEUED, ReplayStatus.RUNNING}:
            raise ValueError(
                "Replay execution identity may only be reserved while active."
            )
        if (
            not replay_execution_id.strip()
            or replay_execution_id == self.source_execution_id
        ):
            raise ValueError(
                "Replay execution ID must differ from source execution ID."
            )
        if self.replay_execution_id and self.replay_execution_id != replay_execution_id:
            raise ValueError("Replay execution ID is immutable once assigned.")
        return replace(self, replay_execution_id=replay_execution_id, updated_at=now)

    def mark_execution_completed(self, now: datetime) -> Replay:
        self._require_status(ReplayStatus.RUNNING, "complete execution")
        if self.replay_execution_id is None:
            raise ValueError("Replay execution ID must be reserved before completion.")
        return replace(
            self,
            status=ReplayStatus.EXECUTION_COMPLETED,
            execution_completed_at=now,
            updated_at=now,
        )

    def request_cancellation(self, now: datetime) -> Replay:
        if self.status not in {
            ReplayStatus.READY,
            ReplayStatus.QUEUED,
            ReplayStatus.RUNNING,
            ReplayStatus.EXECUTION_COMPLETED,
            ReplayStatus.EVALUATING,
            ReplayStatus.COMPARING,
        }:
            raise ValueError(f"Cannot cancel replay in {self.status.value} state.")
        return replace(self, cancel_requested_at=now, updated_at=now)

    def mark_cancelled(self, now: datetime) -> Replay:
        if self.status is ReplayStatus.READY:
            return replace(
                self,
                status=ReplayStatus.CANCELLED,
                cancel_requested_at=self.cancel_requested_at or now,
                cancelled_at=now,
                updated_at=now,
            )
        if (
            self.status
            not in {
                ReplayStatus.QUEUED,
                ReplayStatus.RUNNING,
                ReplayStatus.EXECUTION_COMPLETED,
                ReplayStatus.EVALUATING,
                ReplayStatus.COMPARING,
            }
            or self.cancel_requested_at is None
        ):
            raise ValueError("Replay cancellation must be requested before completion.")
        return replace(
            self,
            status=ReplayStatus.CANCELLED,
            cancelled_at=now,
            updated_at=now,
        )

    def mark_execution_failed(self, failure: ReplayFailure, now: datetime) -> Replay:
        if self.status not in {
            ReplayStatus.READY,
            ReplayStatus.QUEUED,
            ReplayStatus.RUNNING,
            ReplayStatus.EXECUTION_COMPLETED,
            ReplayStatus.EVALUATING,
            ReplayStatus.COMPARING,
        }:
            raise ValueError(f"Cannot fail replay in {self.status.value} state.")
        return replace(
            self,
            status=ReplayStatus.FAILED,
            failure=failure,
            updated_at=now,
        )

    def mark_evaluating(self, evaluation_job_id: str, now: datetime) -> Replay:
        self._require_status(ReplayStatus.EXECUTION_COMPLETED, "start evaluation")
        if not evaluation_job_id.strip():
            raise ValueError("Replay evaluation job ID is required.")
        if self.evaluation_job_id and self.evaluation_job_id != evaluation_job_id:
            raise ValueError("Replay evaluation job ID is immutable once assigned.")
        return replace(
            self,
            status=ReplayStatus.EVALUATING,
            evaluation_job_id=evaluation_job_id,
            evaluation_started_at=now,
            updated_at=now,
        )

    def record_replay_evaluation(self, evaluation_id: str, now: datetime) -> Replay:
        if self.status not in {ReplayStatus.EVALUATING, ReplayStatus.COMPARING}:
            raise ValueError("Replay evaluation may only be recorded while evaluating.")
        return self._record_immutable("replay_evaluation_id", evaluation_id, now)

    def record_baseline_evaluation(self, evaluation_id: str, now: datetime) -> Replay:
        if self.status not in {ReplayStatus.EVALUATING, ReplayStatus.COMPARING}:
            raise ValueError("Replay baseline may only be recorded while evaluating.")
        return self._record_immutable("baseline_evaluation_id", evaluation_id, now)

    def mark_comparing(self, now: datetime) -> Replay:
        self._require_status(ReplayStatus.EVALUATING, "start comparison")
        if not self.replay_evaluation_id or not self.baseline_evaluation_id:
            raise ValueError("Replay and baseline evaluations are required for comparison.")
        return replace(
            self,
            status=ReplayStatus.COMPARING,
            evaluation_completed_at=self.evaluation_completed_at or now,
            comparison_started_at=now,
            updated_at=now,
        )

    def record_comparison(self, comparison_id: str, now: datetime) -> Replay:
        self._require_status(ReplayStatus.COMPARING, "record comparison")
        return self._record_immutable("comparison_id", comparison_id, now)

    def record_drift(self, drift_id: str, now: datetime) -> Replay:
        self._require_status(ReplayStatus.COMPARING, "record drift")
        return self._record_immutable("drift_id", drift_id, now)

    def mark_completed(self, result_id: str, now: datetime) -> Replay:
        self._require_status(ReplayStatus.COMPARING, "complete")
        if not self.comparison_id or not self.drift_id:
            raise ValueError("Comparison and drift evidence are required for completion.")
        completed = self._record_immutable("result_id", result_id, now)
        return replace(
            completed,
            status=ReplayStatus.COMPLETED,
            comparison_completed_at=now,
            completed_at=now,
            updated_at=now,
        )

    def _record_immutable(self, field_name: str, value: str, now: datetime) -> Replay:
        if not value.strip():
            raise ValueError(f"Replay {field_name} is required.")
        current = getattr(self, field_name)
        if current and current != value:
            raise ValueError(f"Replay {field_name} is immutable once assigned.")
        return replace(self, **{field_name: value, "updated_at": now})
