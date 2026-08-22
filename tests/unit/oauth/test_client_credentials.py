from __future__ import annotations

import json
from importlib import import_module
from typing import Any, Self

import pytest

import ai_governance.oauth.client_credentials as oauth
from ai_governance.cli.main import _resolve_walkthrough_token

cli_main_module = import_module("ai_governance.cli.main")


def test_generic_oauth_environment_takes_precedence_over_legacy_names() -> None:
    credentials = oauth.client_credentials_from_environment(
        {
            "AI_GOVERNANCE_OAUTH_TOKEN_URL": "https://issuer.example/token",
            "AI_GOVERNANCE_OAUTH_CLIENT_ID": "walkthrough",
            "AI_GOVERNANCE_OAUTH_CLIENT_SECRET": "walkthrough-secret",
            "AI_GOVERNANCE_MCP_CLIENT_ID": "mcp",
            "AI_GOVERNANCE_MCP_CLIENT_SECRET": "mcp-secret",
            "AI_GOVERNANCE_MCP_TOKEN_URL": "https://issuer.example/mcp-token",
        }
    )

    assert credentials == oauth.OAuthClientCredentials(
        token_url="https://issuer.example/token",
        client_id="walkthrough",
        client_secret="walkthrough-secret",
    )


def test_incomplete_generic_oauth_environment_fails_clearly() -> None:
    with pytest.raises(oauth.OAuthClientCredentialsError, match="missing client_secret"):
        oauth.client_credentials_from_environment(
            {
                "AI_GOVERNANCE_OAUTH_TOKEN_URL": "https://issuer.example/token",
                "AI_GOVERNANCE_OAUTH_CLIENT_ID": "walkthrough",
            }
        )


def test_fetch_access_token_posts_client_credentials_without_logging_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    class Response:
        def read(self) -> bytes:
            return json.dumps({"access_token": "short-lived-token"}).encode()

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["body"] = request.data
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(oauth, "urlopen", fake_urlopen)
    token = oauth.fetch_access_token(
        oauth.OAuthClientCredentials(
            token_url="https://issuer.example/token",
            client_id="walkthrough",
            client_secret="not-logged",
        )
    )

    assert token == "short-lived-token"
    assert observed["url"] == "https://issuer.example/token"
    assert b"grant_type=client_credentials" in observed["body"]
    assert observed["timeout"] == 10


def test_walkthrough_prefers_explicit_token_over_service_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_main_module,
        "access_token_from_environment",
        lambda: (_ for _ in ()).throw(AssertionError("must not be called")),
    )

    assert _resolve_walkthrough_token("user-token") == "user-token"


def test_walkthrough_uses_service_token_when_no_explicit_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_GOVERNANCE_AUTH_MODE", raising=False)
    monkeypatch.setattr(cli_main_module, "access_token_from_environment", lambda: "service-token")

    assert _resolve_walkthrough_token(None) == "service-token"
