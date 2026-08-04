from __future__ import annotations

import pytest

from kavach.api.dependencies.settings import get_api_settings


def test_production_rejects_development_identity(monkeypatch):
    monkeypatch.setenv("KAVACH_ENV", "production")
    monkeypatch.setenv("KAVACH_AUTH_MODE", "development")
    monkeypatch.delenv("KAVACH_ALLOW_DEVELOPMENT_IDENTITY_IN_PRODUCTION", raising=False)
    with pytest.raises(ValueError, match="development identity provider"):
        get_api_settings()
