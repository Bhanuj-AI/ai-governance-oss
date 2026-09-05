"""SQLite persistence for runtime findings."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from threading import Lock
from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.runtime_findings.finding import (
    EvidenceReference,
    FindingLifecycle,
    FindingReview,
    FindingReviewAction,
    FindingSeverity,
    FindingStatus,
    MetricSnapshot,
    ReconciliationOutcome,
    ReconciliationRecord,
    ReconciliationWindow,
    RuntimeFinding,
)
from ai_governance.repositories.runtime_finding_repository import (
    RuntimeFindingCursor,
    RuntimeFindingListFilters,
    RuntimeFindingPage,
    RuntimeFindingRepository,
)


@final
class SQLiteRuntimeFindingRepository(RuntimeFindingRepository):
    """SQLite-backed runtime finding repository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._lock = Lock()

    def save(self, finding: RuntimeFinding) -> RuntimeFinding:
        with self._lock:  # noqa: SIM117 - keep transaction ownership explicit.
            with self._database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO runtime_finding (
                        finding_id, organization_id, project_id, finding_type,
                        subject_type, subject_id, severity, status, lifecycle,
                        baseline_window, observation_window,
                        baseline_metrics_json, observed_metrics_json,
                        observation_count, consecutive_normal_windows, healthy_reconciliation_windows_json, last_reconciliation_json, reviews_json, evidence_references_json,
                        related_execution_ids_json, detector_id, detector_version,
                        first_detected_at, last_detected_at, resolved_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(organization_id, project_id, finding_id) DO UPDATE SET
                        status=excluded.status,
                        lifecycle=excluded.lifecycle,
                        severity=excluded.severity,
                        observed_metrics_json=excluded.observed_metrics_json,
                        observation_count=excluded.observation_count,
                        consecutive_normal_windows=excluded.consecutive_normal_windows,
                        healthy_reconciliation_windows_json=excluded.healthy_reconciliation_windows_json,
                        last_reconciliation_json=excluded.last_reconciliation_json,
                        reviews_json=excluded.reviews_json,
                        last_detected_at=excluded.last_detected_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        finding.finding_id,
                        finding.organization_id,
                        finding.project_id or "",
                        finding.finding_type,
                        finding.subject_type,
                        finding.subject_id,
                        finding.severity.value,
                        finding.status.value,
                        finding.lifecycle.value,
                        finding.baseline_window,
                        finding.observation_window,
                        json.dumps([asdict(m) for m in finding.baseline_metrics], default=str),
                        json.dumps([asdict(m) for m in finding.observed_metrics], default=str),
                        finding.observation_count,
                        finding.consecutive_normal_windows,
                        json.dumps([_window_to_payload(window) for window in finding.healthy_reconciliation_windows]),
                        json.dumps(_record_to_payload(finding.last_reconciliation)) if finding.last_reconciliation else None,
                        json.dumps([_review_to_payload(review) for review in finding.reviews]),
                        json.dumps([asdict(r) for r in finding.evidence_references], default=str),
                        json.dumps(list(finding.related_execution_ids)),
                        finding.detector_id,
                        finding.detector_version,
                        finding.first_detected_at.isoformat() if finding.first_detected_at else None,
                        finding.last_detected_at.isoformat() if finding.last_detected_at else None,
                        finding.resolved_at.isoformat() if finding.resolved_at else None,
                        finding.created_at.isoformat(),
                        finding.updated_at.isoformat(),
                    ),
                )
                connection.commit()
        return finding

    def get(
        self,
        finding_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeFinding | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM runtime_finding WHERE organization_id=? AND project_id=? AND finding_id=?""",
                (organization_id, project_id or "", finding_id),
            ).fetchone()
        if row is None:
            return None
        return _finding_from_row(dict(row))

    def list(
        self,
        filters: RuntimeFindingListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[RuntimeFinding]:
        conditions = ["organization_id=?", "project_id=?"]
        params: list = [organization_id, project_id or ""]

        if filters.finding_type:
            conditions.append("finding_type=?")
            params.append(filters.finding_type)
        if filters.subject_type:
            conditions.append("subject_type=?")
            params.append(filters.subject_type)
        if filters.subject_id:
            conditions.append("subject_id=?")
            params.append(filters.subject_id)
        if filters.severity:
            conditions.append("severity=?")
            params.append(filters.severity.value)
        if filters.status:
            conditions.append("status=?")
            params.append(filters.status.value)
        if filters.created_after:
            conditions.append("created_at>=?")
            params.append(filters.created_after.isoformat())
        if filters.created_before:
            conditions.append("created_at<=?")
            params.append(filters.created_before.isoformat())

        where = " AND ".join(conditions)
        query = f"SELECT * FROM runtime_finding WHERE {where} ORDER BY created_at DESC LIMIT ?"
        params.append(filters.limit)

        with self._database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_finding_from_row(dict(row)) for row in rows]

    def find_by_dedup_key(
        self,
        dedup_key: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeFinding | None:
        # Dedup key is derived from finding_type + org + project + subject_type + subject_id + detector_version
        parts = dedup_key.split(":")
        if len(parts) < 6:
            return None
        finding_type, _org, _proj, subject_type, subject_id, detector_version = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]

        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM runtime_finding WHERE organization_id=? AND project_id=? AND finding_type=? AND subject_type=? AND subject_id=? AND detector_version=?""",
                (organization_id, project_id or "", finding_type, subject_type, subject_id, detector_version),
            ).fetchone()
        if row is None:
            return None
        return _finding_from_row(dict(row))

    def list_by_status(
        self,
        status: FindingStatus,
        organization_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[RuntimeFinding]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM runtime_finding WHERE organization_id=? AND project_id=? AND status=? ORDER BY created_at DESC LIMIT ?""",
                (organization_id, project_id or "", status.value, limit),
            ).fetchall()
        return [_finding_from_row(dict(row)) for row in rows]

    def page_by_status(
        self,
        status: FindingStatus,
        organization_id: str,
        project_id: str | None = None,
        cursor: RuntimeFindingCursor | None = None,
        limit: int = 100,
    ) -> RuntimeFindingPage:
        conditions = ["organization_id=?", "project_id=?", "status=?"]
        params: list[object] = [organization_id, project_id or "", status.value]
        if cursor is not None:
            conditions.append("(created_at < ? OR (created_at = ? AND finding_id < ?))")
            params.extend([cursor.created_at.isoformat(), cursor.created_at.isoformat(), cursor.finding_id])
        params.append(limit + 1)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM runtime_finding WHERE {' AND '.join(conditions)} "
                "ORDER BY created_at DESC, finding_id DESC LIMIT ?",
                params,
            ).fetchall()
        items = tuple(_finding_from_row(dict(row)) for row in rows[:limit])
        return RuntimeFindingPage(
            items=items,
            next_cursor=(RuntimeFindingCursor(items[-1].created_at, items[-1].finding_id) if len(rows) > limit and items else None),
        )

    def finalized_windows_covering(
        self,
        occurred_at: datetime,
        organization_id: str,
        project_id: str | None = None,
    ) -> tuple[ReconciliationWindow, ...]:
        # Finalized decision windows are persisted inside the existing finding
        # lifecycle record. Read all scoped records: a limit here could make
        # a late event's classification depend on record ordering.
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_finding WHERE organization_id=? AND project_id=?",
                (organization_id, project_id or ""),
            ).fetchall()
        windows: list[ReconciliationWindow] = []
        for row in rows:
            finding = _finding_from_row(dict(row))
            candidates = list(finding.healthy_reconciliation_windows)
            if finding.last_reconciliation is not None:
                candidates.append(finding.last_reconciliation.window)
            windows.extend(
                window for window in candidates
                if window.covers(occurred_at)
            )
        return tuple(dict.fromkeys(windows))

    def count_by_subject(
        self,
        subject_type: str,
        subject_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> int:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) as cnt FROM runtime_finding WHERE organization_id=? AND project_id=? AND subject_type=? AND subject_id=?""",
                (organization_id, project_id or "", subject_type, subject_id),
            ).fetchone()
        return int(row["cnt"]) if row else 0


def _finding_from_row(row: dict) -> RuntimeFinding:
    baseline_raw = row.get("baseline_metrics_json")
    observed_raw = row.get("observed_metrics_json")
    evidence_raw = row.get("evidence_references_json")
    exec_ids_raw = row.get("related_execution_ids_json")
    healthy_windows_raw = row.get("healthy_reconciliation_windows_json")
    last_reconciliation_raw = row.get("last_reconciliation_json")
    reviews_raw = row.get("reviews_json")

    baseline_metrics: list[MetricSnapshot] = []
    if baseline_raw:
        try:
            for item in json.loads(baseline_raw):
                baseline_metrics.append(MetricSnapshot(
                    name=item["name"], value=float(item["value"]), sample_size=int(item["sample_size"]),
                ))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    observed_metrics: list[MetricSnapshot] = []
    if observed_raw:
        try:
            for item in json.loads(observed_raw):
                observed_metrics.append(MetricSnapshot(
                    name=item["name"], value=float(item["value"]), sample_size=int(item["sample_size"]),
                ))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    evidence_refs: list[EvidenceReference] = []
    if evidence_raw:
        try:
            for item in json.loads(evidence_raw):
                evidence_refs.append(EvidenceReference(
                    kind=item["kind"], value=item["value"],
                ))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    related_ids: list[str] = []
    if exec_ids_raw:
        try:
            related_ids = json.loads(exec_ids_raw)
        except (json.JSONDecodeError, TypeError):
            pass

    healthy_windows: tuple[ReconciliationWindow, ...] = ()
    if healthy_windows_raw:
        try:
            healthy_windows = tuple(_window_from_payload(item) for item in json.loads(healthy_windows_raw))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            pass

    last_reconciliation: ReconciliationRecord | None = None
    if last_reconciliation_raw:
        try:
            last_reconciliation = _record_from_payload(json.loads(last_reconciliation_raw))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            pass

    reviews: tuple[FindingReview, ...] = ()
    if reviews_raw:
        try:
            reviews = tuple(_review_from_payload(item) for item in json.loads(reviews_raw))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            pass

    lifecycle_raw = row.get("lifecycle")
    lifecycle = FindingLifecycle(
        lifecycle_raw or ("CASE_REVIEW" if row.get("detector_id") == "causal_audit" else "OPERATIONAL")
    )

    return RuntimeFinding(
        finding_id=row["finding_id"],
        organization_id=row["organization_id"],
        project_id=row.get("project_id") or None,
        finding_type=row["finding_type"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        severity=FindingSeverity(row["severity"]),
        status=FindingStatus(row["status"]),
        lifecycle=lifecycle,
        baseline_window=row.get("baseline_window", "7d"),
        observation_window=row.get("observation_window", "24h"),
        baseline_metrics=tuple(baseline_metrics),
        observed_metrics=tuple(observed_metrics),
        observation_count=int(row.get("observation_count", 0)),
        consecutive_normal_windows=(len(healthy_windows) if healthy_windows else int(row.get("consecutive_normal_windows", 0))),
        healthy_reconciliation_windows=healthy_windows,
        last_reconciliation=last_reconciliation,
        reviews=reviews,
        evidence_references=tuple(evidence_refs),
        related_execution_ids=tuple(related_ids),
        detector_id=row.get("detector_id", ""),
        detector_version=row.get("detector_version", "1"),
        first_detected_at=(
            datetime.fromisoformat(row["first_detected_at"])
            if row.get("first_detected_at")
            else None
        ),
        last_detected_at=(
            datetime.fromisoformat(row["last_detected_at"])
            if row.get("last_detected_at")
            else None
        ),
        resolved_at=(
            datetime.fromisoformat(row["resolved_at"])
            if row.get("resolved_at")
            else None
        ),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _window_to_payload(window: ReconciliationWindow) -> dict[str, str | int | None]:
    return {
        "observed_start": window.observed_start.isoformat(),
        "observed_end": window.observed_end.isoformat(),
        "baseline_start": window.baseline_start.isoformat(),
        "baseline_end": window.baseline_end.isoformat(),
        "finalization_cutoff_at": (
            window.finalization_cutoff_at.isoformat()
            if window.finalization_cutoff_at else None
        ),
        "lateness_policy_hours": window.lateness_policy_hours,
    }


def _window_from_payload(payload: dict[str, object]) -> ReconciliationWindow:
    return ReconciliationWindow(
        observed_start=datetime.fromisoformat(payload["observed_start"]),
        observed_end=datetime.fromisoformat(payload["observed_end"]),
        baseline_start=datetime.fromisoformat(payload["baseline_start"]),
        baseline_end=datetime.fromisoformat(payload["baseline_end"]),
        finalization_cutoff_at=(
            datetime.fromisoformat(str(payload["finalization_cutoff_at"]))
            if payload.get("finalization_cutoff_at") else None
        ),
        lateness_policy_hours=(
            int(payload["lateness_policy_hours"])
            if payload.get("lateness_policy_hours") is not None else None
        ),
    )


def _record_to_payload(record: ReconciliationRecord) -> dict[str, object]:
    return {
        "window": _window_to_payload(record.window),
        "outcome": record.outcome.value,
        "reconciled_at": record.reconciled_at.isoformat(),
        "detail": record.detail,
    }


def _record_from_payload(payload: dict[str, object]) -> ReconciliationRecord:
    return ReconciliationRecord(
        window=_window_from_payload(payload["window"]),  # type: ignore[arg-type]
        outcome=ReconciliationOutcome(str(payload["outcome"])),
        reconciled_at=datetime.fromisoformat(str(payload["reconciled_at"])),
        detail=str(payload["detail"]) if payload.get("detail") is not None else None,
    )


def _review_to_payload(review: FindingReview) -> dict[str, str | None]:
    return {
        "action": review.action.value,
        "actor_id": review.actor_id,
        "reviewed_at": review.reviewed_at.isoformat(),
        "note": review.note,
    }


def _review_from_payload(payload: dict[str, object]) -> FindingReview:
    return FindingReview(
        action=FindingReviewAction(str(payload["action"])),
        actor_id=str(payload["actor_id"]),
        reviewed_at=datetime.fromisoformat(str(payload["reviewed_at"])),
        note=str(payload["note"]) if payload.get("note") is not None else None,
    )
