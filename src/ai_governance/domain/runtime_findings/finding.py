"""Runtime Finding aggregate — durable, deterministic operational observations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import Enum


class FindingSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLOSED = "CLOSED"


class FindingLifecycle(str, Enum):
    """How a finding reaches a terminal state."""

    OPERATIONAL = "OPERATIONAL"
    CASE_REVIEW = "CASE_REVIEW"


class FindingReviewAction(str, Enum):
    ACKNOWLEDGE = "ACKNOWLEDGE"
    CLOSE = "CLOSE"


class ReconciliationOutcome(str, Enum):
    """Result of reconciling one completed observation window."""

    HEALTHY_AWAITING = "HEALTHY_AWAITING"
    CONDITION_PRESENT = "CONDITION_PRESENT"
    PROGRESS_RESET = "PROGRESS_RESET"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"
    RESOLVED = "RESOLVED"
    ALREADY_RECONCILED = "ALREADY_RECONCILED"


@dataclass(frozen=True)
class MetricSnapshot:
    name: str
    value: float
    sample_size: int


@dataclass(frozen=True)
class EvidenceReference:
    kind: str
    value: str


@dataclass(frozen=True)
class ReconciliationWindow:
    """A closed, deterministic evidence window used for recovery progress."""

    observed_start: datetime
    observed_end: datetime
    baseline_start: datetime
    baseline_end: datetime
    # These values are a durable snapshot of the finalization contract used
    # for this decision.  They must never be recomputed from a later setting.
    finalization_cutoff_at: datetime | None = None
    lateness_policy_hours: int | None = None

    def __post_init__(self) -> None:
        if self.observed_start >= self.observed_end:
            raise ValueError("A reconciliation observation window must have positive duration.")
        if self.baseline_start >= self.baseline_end:
            raise ValueError("A reconciliation baseline window must have positive duration.")
        if self.baseline_end != self.observed_start:
            raise ValueError("A reconciliation baseline must end when observation begins.")
        if (self.finalization_cutoff_at is None) != (self.lateness_policy_hours is None):
            raise ValueError(
                "A reconciliation finalization cutoff and lateness policy must be recorded together."
            )
        if self.finalization_cutoff_at is not None:
            if self.finalization_cutoff_at < self.observed_end:
                raise ValueError("A reconciliation finalization cutoff cannot precede observation end.")
            if self.lateness_policy_hours is None or self.lateness_policy_hours < 0:
                raise ValueError("A reconciliation lateness policy must be non-negative.")

    def same_evidence_window(self, other: ReconciliationWindow) -> bool:
        """Compare evidence identity without allowing a policy edit to create a retry."""
        return (
            self.observed_start,
            self.observed_end,
            self.baseline_start,
            self.baseline_end,
        ) == (
            other.observed_start,
            other.observed_end,
            other.baseline_start,
            other.baseline_end,
        )

    def covers(self, occurred_at: datetime) -> bool:
        """Whether an event can affect this decision's baseline or observation evidence."""
        timestamp = occurred_at.astimezone(UTC)
        return self.baseline_start <= timestamp < self.observed_end


@dataclass(frozen=True)
class ReconciliationRecord:
    """The latest durable reconciliation result and its source window."""

    window: ReconciliationWindow
    outcome: ReconciliationOutcome
    reconciled_at: datetime
    detail: str | None = None


@dataclass(frozen=True)
class FindingReview:
    action: FindingReviewAction
    actor_id: str
    reviewed_at: datetime
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.actor_id.strip():
            raise ValueError("A finding review requires an actor.")
        if self.note is not None and len(self.note.strip()) > 2_000:
            raise ValueError("A finding review note must not exceed 2,000 characters.")


@dataclass(frozen=True)
class RuntimeFinding:
    """A durable, deterministic observation about agent runtime behaviour."""

    finding_id: str
    organization_id: str
    project_id: str | None = None
    finding_type: str = ""
    subject_type: str = ""
    subject_id: str = ""
    severity: FindingSeverity = FindingSeverity.INFO
    status: FindingStatus = FindingStatus.OPEN
    lifecycle: FindingLifecycle = FindingLifecycle.OPERATIONAL
    baseline_window: str = "7d"
    observation_window: str = "24h"
    baseline_metrics: tuple[MetricSnapshot, ...] = field(default_factory=tuple)
    observed_metrics: tuple[MetricSnapshot, ...] = field(default_factory=tuple)
    observation_count: int = 0
    consecutive_normal_windows: int = 0
    healthy_reconciliation_windows: tuple[ReconciliationWindow, ...] = field(default_factory=tuple)
    last_reconciliation: ReconciliationRecord | None = None
    reviews: tuple[FindingReview, ...] = field(default_factory=tuple)
    evidence_references: tuple[EvidenceReference, ...] = field(default_factory=tuple)
    related_execution_ids: tuple[str, ...] = field(default_factory=tuple)
    detector_id: str = ""
    detector_version: str = "1"
    first_detected_at: datetime | None = None
    last_detected_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.finding_id.strip():
            raise ValueError("finding_id must not be empty.")
        if not self.organization_id.strip():
            raise ValueError("organization_id must not be empty.")
        if not self.finding_type.strip():
            raise ValueError("finding_type must not be empty.")
        if not self.subject_id.strip():
            raise ValueError("subject_id must not be empty.")
        if not self.detector_id.strip():
            raise ValueError("detector_id must not be empty.")
        if len(self.related_execution_ids) > 20:
            object.__setattr__(self, "related_execution_ids", self.related_execution_ids[:20])
        if self.healthy_reconciliation_windows and self.consecutive_normal_windows != len(self.healthy_reconciliation_windows):
            raise ValueError(
                "consecutive_normal_windows must equal retained healthy reconciliation windows."
            )
        if self.lifecycle is FindingLifecycle.OPERATIONAL and self.status not in {
            FindingStatus.OPEN,
            FindingStatus.RESOLVED,
        }:
            raise ValueError("Operational findings cannot use case-review statuses.")
        if self.lifecycle is FindingLifecycle.CASE_REVIEW and self.status not in {
            FindingStatus.OPEN,
            FindingStatus.ACKNOWLEDGED,
            FindingStatus.CLOSED,
        }:
            raise ValueError("Case-review findings cannot use operational resolution.")
        if self.reviews and self.lifecycle is not FindingLifecycle.CASE_REVIEW:
            raise ValueError("Only case-review findings can have review records.")
        if len(self.reviews) > 20:
            object.__setattr__(self, "reviews", self.reviews[-20:])

    def mark_resolved(self, now: datetime | None = None) -> RuntimeFinding:
        if self.lifecycle is not FindingLifecycle.OPERATIONAL:
            raise ValueError("Case-review findings must be closed by review, not reconciliation.")
        now = now or datetime.now(UTC)
        return replace(self, status=FindingStatus.RESOLVED, resolved_at=now, updated_at=now)

    def update_observation(self, now: datetime | None = None) -> RuntimeFinding:
        """Update an observed abnormal finding and reset recovery progress."""
        now = now or datetime.now(UTC)
        return replace(
            self,
            status=FindingStatus.OPEN,
            consecutive_normal_windows=0,
            healthy_reconciliation_windows=(),
            first_detected_at=self.first_detected_at or now,
            last_detected_at=now,
            resolved_at=None,
            updated_at=now,
        )

    def acknowledge(
        self, actor_id: str, note: str | None = None, *, now: datetime | None = None
    ) -> RuntimeFinding:
        if self.lifecycle is not FindingLifecycle.CASE_REVIEW:
            raise ValueError("Only case-review findings can be acknowledged.")
        if self.status is not FindingStatus.OPEN:
            raise ValueError("Only open case-review findings can be acknowledged.")
        now = now or datetime.now(UTC)
        return replace(
            self,
            status=FindingStatus.ACKNOWLEDGED,
            reviews=self.reviews
            + (FindingReview(FindingReviewAction.ACKNOWLEDGE, actor_id, now, note),),
            updated_at=now,
        )

    def close(
        self, actor_id: str, note: str | None = None, *, now: datetime | None = None
    ) -> RuntimeFinding:
        if self.lifecycle is not FindingLifecycle.CASE_REVIEW:
            raise ValueError("Only case-review findings can be closed by review.")
        if self.status not in {FindingStatus.OPEN, FindingStatus.ACKNOWLEDGED}:
            raise ValueError("Only open or acknowledged case-review findings can be closed.")
        now = now or datetime.now(UTC)
        return replace(
            self,
            status=FindingStatus.CLOSED,
            reviews=self.reviews
            + (FindingReview(FindingReviewAction.CLOSE, actor_id, now, note),),
            updated_at=now,
        )

    def record_healthy_window(
        self, window: ReconciliationWindow, *, now: datetime | None = None
    ) -> RuntimeFinding:
        """Record one distinct healthy window; duplicate windows are invalid."""
        now = now or datetime.now(UTC)
        if self.last_reconciliation is not None and self.last_reconciliation.window.same_evidence_window(window):
            raise ValueError("The reconciliation window was already recorded.")
        # Legacy records predate durable window evidence.  Their old counter
        # cannot prove recovery, so a first new window starts a new sequence.
        existing_windows = (
            self.healthy_reconciliation_windows
            if len(self.healthy_reconciliation_windows) == self.consecutive_normal_windows
            else ()
        )
        windows = existing_windows + (window,)
        return replace(
            self,
            consecutive_normal_windows=len(windows),
            healthy_reconciliation_windows=windows,
            last_reconciliation=ReconciliationRecord(
                window=window,
                outcome=ReconciliationOutcome.HEALTHY_AWAITING,
                reconciled_at=now,
            ),
            updated_at=now,
        )

    def record_reconciliation_outcome(
        self,
        window: ReconciliationWindow,
        outcome: ReconciliationOutcome,
        *,
        now: datetime | None = None,
        detail: str | None = None,
        reset_progress: bool = False,
    ) -> RuntimeFinding:
        """Record a non-healthy outcome without interpreting it as healthy."""
        now = now or datetime.now(UTC)
        if self.last_reconciliation is not None and self.last_reconciliation.window.same_evidence_window(window):
            raise ValueError("The reconciliation window was already recorded.")
        return replace(
            self,
            consecutive_normal_windows=0 if reset_progress else self.consecutive_normal_windows,
            healthy_reconciliation_windows=() if reset_progress else self.healthy_reconciliation_windows,
            last_reconciliation=ReconciliationRecord(
                window=window,
                outcome=outcome,
                reconciled_at=now,
                detail=detail,
            ),
            last_detected_at=(now if outcome in {ReconciliationOutcome.CONDITION_PRESENT, ReconciliationOutcome.PROGRESS_RESET} else self.last_detected_at),
            updated_at=now,
        )

    def mark_normal(self) -> RuntimeFinding:
        """Compatibility helper; production reconciliation supplies real windows."""
        now = datetime.now(UTC) + timedelta(microseconds=self.consecutive_normal_windows)
        start = now - timedelta(hours=1)
        return self.record_healthy_window(
            ReconciliationWindow(start, now, start - timedelta(days=7), start), now=now
        )

    def mark_abnormal(self) -> RuntimeFinding:
        """Compatibility helper; production reconciliation supplies real windows."""
        now = datetime.now(UTC)
        start = now - timedelta(hours=1)
        return self.record_reconciliation_outcome(
            ReconciliationWindow(start, now, start - timedelta(days=7), start),
            ReconciliationOutcome.PROGRESS_RESET,
            now=now,
            reset_progress=True,
        )

    @property
    def is_active(self) -> bool:
        return self.status in {FindingStatus.OPEN, FindingStatus.ACKNOWLEDGED}

    @property
    def is_terminal(self) -> bool:
        return self.status in {FindingStatus.RESOLVED, FindingStatus.CLOSED}

    def deduplication_key(self) -> str:
        return (
            f"{self.finding_type}:{self.organization_id}:"
            f"{self.project_id or ''}:{self.subject_type}:{self.subject_id}:"
            f"{self.detector_version}"
        )
