"""OAuth helpers for first-party command-line and automation clients."""

from kavach.oauth.client_credentials import (
    OAuthClientCredentials,
    OAuthClientCredentialsError,
    access_token_from_environment,
    client_credentials_from_environment,
    fetch_access_token,
)

__all__ = [
    "OAuthClientCredentials",
    "OAuthClientCredentialsError",
    "access_token_from_environment",
    "client_credentials_from_environment",
    "fetch_access_token",
]
