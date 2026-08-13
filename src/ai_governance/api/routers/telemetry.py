from __future__ import annotations

from fastapi import APIRouter, Depends

from ai_governance.api.dependencies.telemetry import get_telemetry_service
from ai_governance.api.models.telemetry import TelemetryPreviewResponse, TelemetryStatusResponse
from ai_governance.services.telemetry_service import TelemetryService

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry"])


@router.get("/status", response_model=TelemetryStatusResponse, summary="Read anonymous telemetry status")
def telemetry_status(service: TelemetryService = Depends(get_telemetry_service)) -> TelemetryStatusResponse:
    return TelemetryStatusResponse(**service.status())


@router.get("/preview", response_model=TelemetryPreviewResponse, summary="Preview exact sanitized telemetry payloads")
def telemetry_preview(service: TelemetryService = Depends(get_telemetry_service)) -> TelemetryPreviewResponse:
    """This endpoint is read-only and does not enqueue or transmit telemetry."""
    return TelemetryPreviewResponse(payloads=service.preview())
