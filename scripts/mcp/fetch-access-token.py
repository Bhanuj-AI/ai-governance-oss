#!/usr/bin/env python3
"""Compatibility wrapper for the generic OAuth token helper.

Use ``scripts/oauth/fetch-access-token.py`` for new automation.
"""

import subprocess
from pathlib import Path

from dotenv import load_dotenv
from kavach.oauth import OAuthClientCredentialsError, access_token_from_environment


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env.local")

try:
    token = access_token_from_environment()
except OAuthClientCredentialsError as exc:
    raise SystemExit(f"OAuth token request failed: {exc}") from exc
if token is None:
    raise SystemExit("OAuth token request failed: configure KAVACH_MCP_* credentials.")

subprocess.run(["pbcopy"], input=token.encode(), check=True)
print("Access token copied to clipboard. Prefer scripts/oauth/fetch-access-token.py for new use.")
