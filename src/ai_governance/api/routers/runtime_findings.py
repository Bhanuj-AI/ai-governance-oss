"""REST API for deterministic runtime findings.

Endpoints:
    GET    /api/v1/runtime-findings          — list findings with filters
    GET    /api/v1/runtime-findings/{id}     — get finding detail
    POST   /api/v1/runtime-findings/detect   — trigger detection run
    POST   /api/v1/runtime-findings/reconcile — reconcile active findings
"""

from __future__ import annotations

from datetime import datetime as _dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ai_governance.api.dependencies.authorization import enforce_permission
from ai_governance.api.dependencies.runtime_findings import (
    get_runtime_finding_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models.runtime_finding import (
    EvidenceReferenceResponse,
    FindingReviewResponse,
    MetricSnapshotResponse,
    ReconciliationFindingResponse,
    ReconciliationRecordResponse,
    ReconciliationWindowResponse,
    RuntimeFindingListResponse,
    RuntimeFindingReconcileResponse,
    RuntimeFindingResponse,
    RuntimeFindingReviewRequest,
)
from ai_governance.domain.runtime_findings.finding import (
    FindingReviewAction,
    FindingSeverity,
    FindingStatus,
)
from ai_governance.services.runtime_finding_service import (
    RuntimeFindingService,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.permissions import Permission

router = APIRouter(
    prefix="/api/v1/runtime-findings",
    tags=["Runtime findings"],
)


def _finding_to_response(finding: object) -> RuntimeFindingResponse:
    return RuntimeFindingResponse(
        finding_id=finding.finding_id,
        organization_id=finding.organization_id,
        project_id=finding.project_id,
        finding_type=finding.finding_type,
        subject_type=finding.subject_type,
        subject_id=finding.subject_id,
        severity=finding.severity.value if hasattr(finding.severity, "value") else finding.severity,
        status=finding.status.value if hasattr(finding.status, "value") else finding.status,
        lifecycle=finding.lifecycle.value if hasattr(finding.lifecycle, "value") else finding.lifecycle,
        baseline_window=finding.baseline_window,
        observation_window=finding.observation_window,
        baseline_metrics=[
            MetricSnapshotResponse(
                name=m.name, value=m.value, sample_size=m.sample_size
            )
            for m in finding.baseline_metrics
        ],
        observed_metrics=[
            MetricSnapshotResponse(
                name=m.name, value=m.value, sample_size=m.sample_size
            )
            for m in finding.observed_metrics
        ],
        observation_count=finding.observation_count,
        consecutive_normal_windows=finding.consecutive_normal_windows,
        healthy_reconciliation_windows=[
            ReconciliationWindowResponse(
                observed_start=window.observed_start, observed_end=window.observed_end,
                baseline_start=window.baseline_start, baseline_end=window.baseline_end,
                finalization_cutoff_at=window.finalization_cutoff_at,
                lateness_policy_hours=window.lateness_policy_hours,
            ) for window in finding.healthy_reconciliation_windows
        ],
        last_reconciliation=(
            ReconciliationRecordResponse(
                window=ReconciliationWindowResponse(
                    observed_start=finding.last_reconciliation.window.observed_start,
                    observed_end=finding.last_reconciliation.window.observed_end,
                    baseline_start=finding.last_reconciliation.window.baseline_start,
                    baseline_end=finding.last_reconciliation.window.baseline_end,
                    finalization_cutoff_at=finding.last_reconciliation.window.finalization_cutoff_at,
                    lateness_policy_hours=finding.last_reconciliation.window.lateness_policy_hours,
                ),
                outcome=finding.last_reconciliation.outcome.value,
                reconciled_at=finding.last_reconciliation.reconciled_at,
                detail=finding.last_reconciliation.detail,
            ) if finding.last_reconciliation else None
        ),
        reviews=[
            FindingReviewResponse(
                action=review.action.value,
                actor_id=review.actor_id,
                reviewed_at=review.reviewed_at,
                note=review.note,
            ) for review in finding.reviews
        ],
        evidence_references=[
            EvidenceReferenceResponse(kind=r.kind, value=r.value)
            for r in finding.evidence_references
        ],
        related_execution_ids=list(finding.related_execution_ids),
        detector_id=finding.detector_id,
        detector_version=finding.detector_version,
        first_detected_at=finding.first_detected_at,
        last_detected_at=finding.last_detected_at,
        resolved_at=finding.resolved_at,
        created_at=finding.created_at,
        updated_at=finding.updated_at,
    )


@router.get("", response_model=RuntimeFindingListResponse)
def list_runtime_findings(
    service: Annotated[RuntimeFindingService, Depends(get_runtime_finding_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.RUNTIME_FINDING_READ)),
    finding_type: str | None = Query(None, min_length=1),
    subject_type: str | None = Query(None, min_length=1),
    subject_id: str | None = Query(None, min_length=1),
    severity: str | None = Query(None, min_length=1),
    status_filter: str | None = Query(None, alias="status", min_length=1),
    created_after: str | None = Query(None),
    created_before: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> RuntimeFindingListResponse:
    """List runtime findings with filtering."""
    severity_filter = None
    if severity is not None:
        try:
            severity_filter = FindingSeverity(severity)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity filter '{severity}'.",
            )

    status_value = None
    if status_filter is not None:
        try:
            status_value = FindingStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter '{status_filter}'.",
            )

    findings = service.list_findings(
        organization_id=context.organization_id,
        project_id=context.project_id,
        finding_type=finding_type,
        subject_type=subject_type,
        subject_id=subject_id,
        severity=severity_filter,
        status=status_value,
        created_after=_dt.fromisoformat(created_after) if created_after else None,
        created_before=_dt.fromisoformat(created_before) if created_before else None,
        limit=limit,
    )

    return RuntimeFindingListResponse(
        items=[_finding_to_response(f) for f in findings],
    )


@router.get("/{finding_id}", response_model=RuntimeFindingResponse)
def get_runtime_finding(
    finding_id: str,
    service: Annotated[RuntimeFindingService, Depends(get_runtime_finding_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.RUNTIME_FINDING_READ)),
) -> RuntimeFindingResponse:
    """Get a runtime finding by ID."""
    finding = service._finding_repo.get(
        finding_id, context.organization_id, context.project_id
    )
    if finding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found.",
        )
    return _finding_to_response(finding)


@router.post("/{finding_id}/review", response_model=RuntimeFindingResponse)
def review_runtime_finding(
    finding_id: str,
    request: RuntimeFindingReviewRequest,
    service: Annotated[RuntimeFindingService, Depends(get_runtime_finding_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.RUNTIME_FINDING_REVIEW)),
) -> RuntimeFindingResponse:
    """Acknowledge or close a historical case-review finding."""
    try:
        action = FindingReviewAction(request.action)
        finding = service.review_case_finding(
            finding_id,
            action,
            context.actor_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            note=request.note,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _finding_to_response(finding)


@router.post("/detect", status_code=status.HTTP_202_ACCEPTED)
def trigger_detection(
    service: Annotated[RuntimeFindingService, Depends(get_runtime_finding_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.RUNTIME_FINDING_DETECT)),
) -> dict[str, object]:
    """Trigger a detection run."""
    findings = service.run_detection(
        context.organization_id, context.project_id
    )
    return {
        "status": "accepted",
        "findings_created": len(findings),
    }


@router.post("/reconcile", response_model=RuntimeFindingReconcileResponse)
def reconcile_findings(
    service: Annotated[RuntimeFindingService, Depends(get_runtime_finding_service)],
    context: TenantContext = Depends(get_compatible_tenant_context),
    _: object = Depends(enforce_permission(Permission.RUNTIME_FINDING_RECONCILE)),
) -> RuntimeFindingReconcileResponse:
    """Reconcile active findings — resolve those whose condition no longer holds."""
    result = service.reconcile_active_findings(
        context.organization_id, context.project_id
    )
    return RuntimeFindingReconcileResponse(
        reconciled=len(result),
        resolved=len(result),
        processed=len(result.outcomes),
        outcomes={
            outcome.value: sum(1 for item in result.outcomes if item.outcome == outcome)
            for outcome in {item.outcome for item in result.outcomes}
        },
        findings=[
            ReconciliationFindingResponse(
                finding_id=item.finding_id,
                outcome=item.outcome.value,
                consecutive_normal_windows=item.consecutive_normal_windows,
                required_normal_windows=item.required_normal_windows,
                window=(
                    ReconciliationWindowResponse(
                        observed_start=item.window.observed_start,
                        observed_end=item.window.observed_end,
                        baseline_start=item.window.baseline_start,
                        baseline_end=item.window.baseline_end,
                        finalization_cutoff_at=item.window.finalization_cutoff_at,
                        lateness_policy_hours=item.window.lateness_policy_hours,
                    ) if item.window else None
                ),
                detail=item.detail,
            ) for item in result.outcomes
        ],
    )
