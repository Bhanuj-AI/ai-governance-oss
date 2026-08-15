#!/usr/bin/env python3
"""Fetch a local service-account token for the native MCP resource."""

import subprocess
from pathlib import Path

from dotenv import dotenv_values

from ai_governance.oauth import (
    OAuthClientCredentials,
    OAuthClientCredentialsError,
    fetch_access_token,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
OAUTH_ENV = ROOT_DIR / ".env.oauth.generated"


def _required(values: dict[str, str | None], name: str) -> str:
    value = values.get(name)
    if not value:
        raise OAuthClientCredentialsError(
            f"{name} is required in {OAUTH_ENV.name}; run ./servers.sh up first."
        )
    return value


try:
    values = dotenv_values(OAUTH_ENV)
    credentials = OAuthClientCredentials(
        token_url=_required(values, "AI_GOVERNANCE_MCP_TOKEN_URL"),
        client_id=_required(values, "AI_GOVERNANCE_MCP_CLIENT_ID"),
        client_secret=_required(values, "AI_GOVERNANCE_MCP_CLIENT_SECRET"),
    )
    token = fetch_access_token(credentials)
except OAuthClientCredentialsError as exc:
    raise SystemExit(f"OAuth token request failed: {exc}") from exc

subprocess.run(["pbcopy"], input=token.encode(), check=True)
print("MCP access token copied to clipboard.")
