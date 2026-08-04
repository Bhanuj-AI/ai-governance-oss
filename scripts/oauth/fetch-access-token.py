#!/usr/bin/env python3
"""Fetch a short-lived OAuth service token without writing it to disk or stdout."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from kavach.oauth import OAuthClientCredentialsError, access_token_from_environment


ROOT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a short-lived OAuth client-credentials access token."
    )
    parser.add_argument(
        "--clipboard",
        action="store_true",
        help="Copy the token to the macOS clipboard instead of displaying it.",
    )
    arguments = parser.parse_args()
    load_dotenv(ROOT_DIR / ".env.local", override=False)
    load_dotenv(ROOT_DIR / ".env.oauth.generated", override=False)
    try:
        token = access_token_from_environment()
    except OAuthClientCredentialsError as exc:
        parser.exit(1, f"OAuth token request failed: {exc}\n")
    if token is None:
        parser.exit(
            1,
            "OAuth token request failed: configure KAVACH_OAUTH_* credentials "
            "(or the local KAVACH_MCP_* compatibility variables).\n",
        )
    if arguments.clipboard:
        subprocess.run(["pbcopy"], input=token.encode(), check=True)
        print("Short-lived access token copied to clipboard.")
        return
    print("Short-lived access token obtained. Pass --clipboard to copy it on macOS.")


if __name__ == "__main__":
    main()
