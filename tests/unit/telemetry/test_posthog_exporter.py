from __future__ import annotations

from datetime import UTC, datetime
from urllib.error import HTTPError, URLError

import pytest

from ai_governance.domain.telemetry import (
    TelemetryCategory,
    TelemetryMetric,
    TelemetrySnapshot,
)
from ai_governance.telemetry.exporters.posthog import PostHogTelemetryExporter


def _snapshot() -> TelemetrySnapshot:
    return TelemetrySnapshot(
        installation_id="81eb1e84-0000-4000-8000-000000000000",
        ai_governance_version="1.0.0",
        period_start=datetime(2026, 8, 13, tzinfo=UTC),
        period_end=datetime(2026, 8, 14, tzinfo=UTC),
        category=TelemetryCategory.PRODUCT_ANALYTICS,
        metrics=((TelemetryMetric.GOVERNED_EXECUTIONS, 12),),
    )


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_posthog_exporter_delivers_sanitized_snapshot(monkeypatch) -> None:
    seen = {}

    def fake_urlopen(request, timeout):
        seen["body"] = request.data.decode("utf-8")
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("ai_governance.telemetry.exporters.posthog.urlopen", fake_urlopen)
    result = PostHogTelemetryExporter("secret", timeout_seconds=2).export(_snapshot())

    assert result.delivered
    assert seen["timeout"] == 2
    assert "governed_executions" in seen["body"]
    assert "tenant" not in seen["body"]


@pytest.mark.parametrize(
    ("failure", "retryable"),
    [
        (HTTPError("https://example.test", 400, "bad", {}, None), False),
        (HTTPError("https://example.test", 500, "bad", {}, None), True),
        (URLError("unavailable"), True),
        (TimeoutError(), True),
    ],
)
def test_posthog_exporter_isolates_delivery_failures(monkeypatch, failure, retryable: bool) -> None:
    def fake_urlopen(request, timeout):
        raise failure

    monkeypatch.setattr("ai_governance.telemetry.exporters.posthog.urlopen", fake_urlopen)
    result = PostHogTelemetryExporter("secret").export(_snapshot())

    assert not result.delivered
    assert result.retryable is retryable


def test_posthog_exporter_requires_https() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        PostHogTelemetryExporter("secret", endpoint="http://example.test")
