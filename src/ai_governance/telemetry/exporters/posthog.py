"""Small PostHog HTTP adapter; no PostHog SDK leaks into application code."""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ai_governance.domain.telemetry import (
    TelemetryCategory,
    TelemetryExportResult,
    TelemetrySnapshot,
)
from ai_governance.telemetry.privacy import TelemetryPrivacyGuard

_LOGGER = logging.getLogger(__name__)


class PostHogTelemetryExporter:
    def __init__(self, api_key: str, endpoint: str = "https://us.i.posthog.com/capture/", timeout_seconds: float = 3.0) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("PostHog telemetry endpoint must use HTTPS.")
        if not api_key.strip():
            raise ValueError("PostHog API key is required.")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("Telemetry timeout must be between 0 and 30 seconds.")
        self._api_key, self._endpoint, self._timeout_seconds = api_key, endpoint, timeout_seconds

    def export(self, snapshot: TelemetrySnapshot) -> TelemetryExportResult:
        event = {
            TelemetryCategory.ESSENTIAL: "ai_governance_installation",
            TelemetryCategory.PRODUCT_ANALYTICS: "ai_governance_usage_daily",
            TelemetryCategory.PERFORMANCE_RESEARCH: "ai_governance_performance_daily",
        }[snapshot.category]
        payload = TelemetryPrivacyGuard().serialize(snapshot)
        body = json.dumps({
            "api_key": self._api_key,
            "event": event,
            "distinct_id": snapshot.installation_id,
            "properties": payload,
        }).encode("utf-8")
        request = Request(self._endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # nosec B310 - validated HTTPS endpoint
                status = response.status
            return TelemetryExportResult(delivered=200 <= status < 300, retryable=status >= 500, status_code=status)
        except HTTPError as exc:
            return TelemetryExportResult(delivered=False, retryable=exc.code >= 500, status_code=exc.code, error_code="HTTP_ERROR")
        except (URLError, TimeoutError, OSError):
            _LOGGER.warning("telemetry_export_unavailable", extra={"exporter": "posthog"})
            return TelemetryExportResult(delivered=False, retryable=True, error_code="NETWORK_UNAVAILABLE")
