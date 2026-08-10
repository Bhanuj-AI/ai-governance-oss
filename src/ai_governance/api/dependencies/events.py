"""Application-scoped generic domain-event dependency wiring."""

from __future__ import annotations

from fastapi import Request

from ai_governance.events import EventPublisher


def get_event_publisher(request: Request) -> EventPublisher:
    """Return the current application's extension-owned event publisher."""
    return request.app.state.extension_registry.events
