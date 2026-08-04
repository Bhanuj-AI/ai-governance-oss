"""Runtime diagnostics for the public Kavach extension framework."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from kavach.api.dependencies.authorization import enforce_permission
from kavach.tenancy.permissions import Permission

router = APIRouter(prefix="/api/v1/runtime", tags=["Runtime"])


@router.get(
    "/extensions",
    summary="Extension runtime diagnostics",
    dependencies=[Depends(enforce_permission(Permission.SETTINGS_READ))],
)
def extensions(request: Request) -> dict[str, Any]:
    """Return a settings-reader's secret-free extension runtime snapshot.

    The endpoint is an operational diagnostic rather than a configuration API.
    It reports plugin compatibility/lifecycle state, selected provider owners,
    route claims, and recent hook/event outcomes, while deliberately excluding
    concrete objects, callbacks, credentials, and plugin-private settings.
    """
    return request.app.state.extension_registry.diagnostics()
