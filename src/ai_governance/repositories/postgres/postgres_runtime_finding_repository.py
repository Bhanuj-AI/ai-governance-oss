"""PostgreSQL persistence for runtime findings."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
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
class PostgresRuntimeFindingRepository(RuntimeFindingRepository):
    """PostgreSQL-backed runtime finding repository."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, finding: RuntimeFinding) -> RuntimeFinding:
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
                ) VALUES (
                    %(finding_id)s, %(organization_id)s, %(project_id)s, %(finding_type)s,
                    %(subject_type)s, %(subject_id)s, %(severity)s, %(status)s, %(lifecycle)s,
                    %(baseline_window)s, %(observation_window)s,
                    %(baseline_metrics_json)s, %(observed_metrics_json)s,
                    %(observation_count)s, %(consecutive_normal_windows)s, %(healthy_reconciliation_windows_json)s, %(last_reconciliation_json)s, %(reviews_json)s, %(evidence_references_json)s,
                    %(related_execution_ids_json)s, %(detector_id)s, %(detector_version)s,
                    %(first_detected_at)s, %(last_detected_at)s, %(resolved_at)s,
                    %(created_at)s, %(updated_at)s
                ) ON CONFLICT (organization_id, project_id, finding_id) DO UPDATE SET
                    status=EXCLUDED.status,
                    lifecycle=EXCLUDED.lifecycle,
                    severity=EXCLUDED.severity,
                    observed_metrics_json=EXCLUDED.observed_metrics_json,
                    observation_count=EXCLUDED.observation_count,
                    consecutive_normal_windows=EXCLUDED.consecutive_normal_windows,
                    healthy_reconciliation_windows_json=EXCLUDED.healthy_reconciliation_windows_json,
                    last_reconciliation_json=EXCLUDED.last_reconciliation_json,
                    reviews_json=EXCLUDED.reviews_json,
                    last_detected_at=EXCLUDED.last_detected_at,
                    updated_at=EXCLUDED.updated_at
                """,
                {
                    "finding_id": finding.finding_id,
                    "organization_id": finding.organization_id,
                    "project_id": finding.project_id or "",
                    "finding_type": finding.finding_type,
                    "subject_type": finding.subject_type,
                    "subject_id": finding.subject_id,
                    "severity": finding.severity.value,
                    "status": finding.status.value,
                    "lifecycle": finding.lifecycle.value,
                    "baseline_window": finding.baseline_window,
                    "observation_window": finding.observation_window,
                    "baseline_metrics_json": json.dumps(
                        [asdict(m) for m in finding.baseline_metrics], default=str
                    ),
                    "observed_metrics_json": json.dumps(
                        [asdict(m) for m in finding.observed_metrics], default=str
                    ),
                    "observation_count": finding.observation_count,
                    "consecutive_normal_windows": finding.consecutive_normal_windows,
                    "healthy_reconciliation_windows_json": json.dumps([_window_to_payload(window) for window in finding.healthy_reconciliation_windows]),
                    "last_reconciliation_json": json.dumps(_record_to_payload(finding.last_reconciliation)) if finding.last_reconciliation else None,
                    "reviews_json": json.dumps([_review_to_payload(review) for review in finding.reviews]),
                    "evidence_references_json": json.dumps(
                        [asdict(r) for r in finding.evidence_references], default=str
                    ),
                    "related_execution_ids_json": json.dumps(list(finding.related_execution_ids)),
                    "detector_id": finding.detector_id,
                    "detector_version": finding.detector_version,
                    "first_detected_at": (
                        finding.first_detected_at.isoformat() if finding.first_detected_at else None
                    ),
                    "last_detected_at": (
                        finding.last_detected_at.isoformat() if finding.last_detected_at else None
                    ),
                    "resolved_at": (
                        finding.resolved_at.isoformat() if finding.resolved_at else None
                    ),
                    "created_at": finding.created_at.isoformat(),
                    "updated_at": finding.updated_at.isoformat(),
                },
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
                """SELECT * FROM runtime_finding WHERE organization_id=%(organization_id)s AND project_id=%(project_id)s AND finding_id=%(finding_id)s""",
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "finding_id": finding_id,
                },
            ).fetchone()
        if row is None:
            return None
        return _finding_from_row(row)

    def list(
        self,
        filters: RuntimeFindingListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[RuntimeFinding]:
        conditions = ["organization_id=%(organization_id)s", "project_id=%(project_id)s"]
        params: dict = {
            "organization_id": organization_id,
            "project_id": project_id or "",
        }

        if filters.finding_type:
            conditions.append("finding_type=%(finding_type)s")
            params["finding_type"] = filters.finding_type
        if filters.subject_type:
            conditions.append("subject_type=%(subject_type)s")
            params["subject_type"] = filters.subject_type
        if filters.subject_id:
            conditions.append("subject_id=%(subject_id)s")
            params["subject_id"] = filters.subject_id
        if filters.severity:
            conditions.append("severity=%(severity)s")
            params["severity"] = filters.severity.value
        if filters.status:
            conditions.append("status=%(status)s")
            params["status"] = filters.status.value
        if filters.created_after:
            conditions.append("created_at>=%(created_after)s")
            params["created_after"] = filters.created_after.isoformat()
        if filters.created_before:
            conditions.append("created_at<=%(created_before)s")
            params["created_before"] = filters.created_before.isoformat()

        where = " AND ".join(conditions)
        query = f"SELECT * FROM runtime_finding WHERE {where} ORDER BY created_at DESC LIMIT %(limit)s"
        params["limit"] = filters.limit

        with self._database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_finding_from_row(row) for row in rows]

    def find_by_dedup_key(
        self,
        dedup_key: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeFinding | None:
        parts = dedup_key.split(":")
        if len(parts) < 6:
            return None
        finding_type, _org, _proj, subject_type, subject_id, detector_version = (
            parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
        )

        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT * FROM runtime_finding WHERE organization_id=%(organization_id)s AND project_id=%(project_id)s AND finding_type=%(finding_type)s AND subject_type=%(subject_type)s AND subject_id=%(subject_id)s AND detector_version=%(detector_version)s""",
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "finding_type": finding_type,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "detector_version": detector_version,
                },
            ).fetchone()
        if row is None:
            return None
        return _finding_from_row(row)

    def list_by_status(
        self,
        status: FindingStatus,
        organization_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[RuntimeFinding]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM runtime_finding WHERE organization_id=%(organization_id)s AND project_id=%(project_id)s AND status=%(status)s ORDER BY created_at DESC LIMIT %(limit)s""",
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "status": status.value,
                    "limit": limit,
                },
            ).fetchall()
        return [_finding_from_row(row) for row in rows]

    def page_by_status(
        self,
        status: FindingStatus,
        organization_id: str,
        project_id: str | None = None,
        cursor: RuntimeFindingCursor | None = None,
        limit: int = 100,
    ) -> RuntimeFindingPage:
        conditions = ["organization_id=%(organization_id)s", "project_id=%(project_id)s", "status=%(status)s"]
        params: dict[str, object] = {
            "organization_id": organization_id,
            "project_id": project_id or "",
            "status": status.value,
            "limit": limit + 1,
        }
        if cursor is not None:
            conditions.append("(created_at < %(cursor_created_at)s OR (created_at = %(cursor_created_at)s AND finding_id < %(cursor_finding_id)s))")
            params["cursor_created_at"] = cursor.created_at.isoformat()
            params["cursor_finding_id"] = cursor.finding_id
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM runtime_finding WHERE {' AND '.join(conditions)} "
                "ORDER BY created_at DESC, finding_id DESC LIMIT %(limit)s",
                params,
            ).fetchall()
        items = tuple(_finding_from_row(row) for row in rows[:limit])
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
        # Do not apply a page limit: all historical decision windows in scope
        # are authoritative for this late-event classification.
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtime_finding WHERE organization_id=%(organization_id)s AND project_id=%(project_id)s",
                {"organization_id": organization_id, "project_id": project_id or ""},
            ).fetchall()
        windows: list[ReconciliationWindow] = []
        for row in rows:
            finding = _finding_from_row(row)
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
                """SELECT COUNT(*) as cnt FROM runtime_finding WHERE organization_id=%(organization_id)s AND project_id=%(project_id)s AND subject_type=%(subject_type)s AND subject_id=%(subject_id)s""",
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                },
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
            healthy_windows = tuple(_window_from_payload(item) for item in _load_json(healthy_windows_raw))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            pass

    last_reconciliation: ReconciliationRecord | None = None
    if last_reconciliation_raw:
        try:
            last_reconciliation = _record_from_payload(_load_json(last_reconciliation_raw))
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            pass

    reviews: tuple[FindingReview, ...] = ()
    if reviews_raw:
        try:
            reviews = tuple(_review_from_payload(item) for item in _load_json(reviews_raw))
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


def _load_json(value: object) -> object:
    """psycopg may return JSONB as an object while SQLite returns text."""
    return value if isinstance(value, (dict, list)) else json.loads(value)
