"""Small, dependency-free OAuth 2.0 client-credentials support."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class OAuthClientCredentialsError(Exception):
    """Client credentials are absent, invalid, or rejected by the issuer."""


@dataclass(frozen=True)
class OAuthClientCredentials:
    """Configuration for a confidential OAuth client; never serialize this."""

    token_url: str
    client_id: str
    client_secret: str


def client_credentials_from_environment(
    environment: Mapping[str, str] | None = None,
) -> OAuthClientCredentials | None:
    """Read generic OAuth settings, with a local MCP compatibility fallback.

    ``KAVACH_OAUTH_*`` is the supported workload-neutral interface. The MCP
    names remain a temporary local-development fallback so existing installs do
    not need to copy credentials merely to run the walkthrough.
    """
    values = environment if environment is not None else os.environ
    generic = {
        "token_url": values.get("KAVACH_OAUTH_TOKEN_URL"),
        "client_id": values.get("KAVACH_OAUTH_CLIENT_ID"),
        "client_secret": values.get("KAVACH_OAUTH_CLIENT_SECRET"),
    }
    if any(generic.values()):
        missing = [name for name, value in generic.items() if not value]
        if missing:
            raise OAuthClientCredentialsError(
                "Incomplete KAVACH_OAUTH client-credentials configuration: "
                f"missing {', '.join(missing)}."
            )
        return OAuthClientCredentials(**generic)  # type: ignore[arg-type]

    legacy = {
        "token_url": values.get("KAVACH_MCP_TOKEN_URL"),
        "client_id": values.get("KAVACH_MCP_CLIENT_ID"),
        "client_secret": values.get("KAVACH_MCP_CLIENT_SECRET"),
    }
    if all(legacy.values()):
        return OAuthClientCredentials(**legacy)  # type: ignore[arg-type]
    return None


def access_token_from_environment(
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """Exchange configured workload credentials for one short-lived access token."""
    credentials = client_credentials_from_environment(environment)
    return fetch_access_token(credentials) if credentials else None


def fetch_access_token(credentials: OAuthClientCredentials) -> str:
    """Exchange client credentials without logging, persisting, or returning secrets."""
    body = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
        }
    ).encode()
    request = Request(
        credentials.token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload: Any = json.load(response)
    except HTTPError as exc:
        raise OAuthClientCredentialsError(
            f"OAuth token endpoint rejected client credentials (HTTP {exc.code})."
        ) from exc
    except URLError as exc:
        raise OAuthClientCredentialsError(
            f"OAuth token endpoint is unavailable: {exc.reason}."
        ) from exc

    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise OAuthClientCredentialsError(
            "OAuth token response did not contain an access_token."
        )
    return token
