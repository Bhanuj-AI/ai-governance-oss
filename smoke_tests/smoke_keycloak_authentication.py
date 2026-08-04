#!/usr/bin/env python3
"""
Smoke test for Keycloak OIDC authentication integration.

Tests the full authentication pipeline:
  1. Development mode (existing header-based behaviour)
  2. Keycloak mode — service account token validation
  3. Keycloak mode — error cases (missing, expired, invalid issuer)
  4. Full pipeline: JWT → AuthenticatedPrincipal → TenantContext

Usage
-----
    # Development mode (default)
    python smoke_tests/smoke_keycloak_authentication.py

    # Keycloak mode against a running Keycloak instance
    KAVACH_AUTH_MODE=keycloak \\
    KAVACH_OIDC_ISSUER=http://localhost:8080/realms/kavach \\
    python smoke_tests/smoke_keycloak_authentication.py

Requirements
------------
- Keycloak running at http://localhost:8080 with realm "kavach"
- Client "kavach-service" configured with client_credentials grant
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.request

from kavach.tenancy.authentication import (
    AuthenticationError,
    AuthenticationService,
)
from kavach.tenancy.context_factory import TenantContextFactory
from kavach.tenancy.domain import AuthenticatedPrincipal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _get_keycloak_token(
    client_id: str = "kavach-service",
    client_secret: str = "secret",
) -> dict:
    """Fetch an access token from Keycloak."""
    issuer = os.getenv("KAVACH_OIDC_ISSUER")
    token_url = f"{issuer}/protocol/openid-connect/token"

    req = urllib.request.Request(
        token_url,
        data=f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}".encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def _make_fake_jwt(
    sub: str = "user-1",
    iss: str = "http://localhost:8080/realms/kavach",
    exp: int | None = None,
    azp: str = "kavach-service",
    principal_type: str = "USER",
    organization_id: str | None = None,
    kid: str = "test-key",
    alg: str = "RS256",
) -> str:
    """Build a fake JWT (signature intentionally invalid — used for error-case tests)."""
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    header_b64 = _b64url_encode(json.dumps(header).encode())

    payload: dict = {
        "sub": sub,
        "iss": iss,
        "azp": azp,
        "principal_type": principal_type,
    }
    if exp is not None:
        payload["exp"] = exp
    elif "exp" not in payload:
        payload["exp"] = int(time.time()) + 3600
    if organization_id is not None:
        payload["organization_id"] = organization_id

    payload_b64 = _b64url_encode(json.dumps(payload).encode())
    sig_b64 = _b64url_encode(b"\x00" * 256)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_development_mode() -> None:
    """Development mode should work without JWT — actor from env."""
    print("[test_development_mode]")

    _orig_auth_mode = os.environ.get("KAVACH_AUTH_MODE")
    _orig_oidc_issuer = os.environ.get("KAVACH_OIDC_ISSUER")
    try:
        os.environ["KAVACH_AUTH_MODE"] = "development"
        os.environ.pop("KAVACH_OIDC_ISSUER", None)

        # Clear cached dependencies
        import kavach.api.dependencies.authentication as auth_mod
        auth_mod.get_authentication_service.cache_clear()

        from kavach.api.dependencies.authentication import get_authenticated_principal

        class FakeRequest:
            pass

        principal = get_authenticated_principal(authorization=None, request=FakeRequest())

        assert isinstance(principal, AuthenticatedPrincipal)
        assert principal.subject == os.getenv("KAVACH_DEVELOPMENT_ACTOR_ID")
        assert principal.principal_type.value == "SYSTEM"
        print(f"  subject={principal.subject}")
        print(f"  principal_type={principal.principal_type.value}")
        print("  PASSED")
    finally:
        if _orig_auth_mode is not None:
            os.environ["KAVACH_AUTH_MODE"] = _orig_auth_mode
        elif "KAVACH_AUTH_MODE" in os.environ:
            del os.environ["KAVACH_AUTH_MODE"]
        if _orig_oidc_issuer is not None:
            os.environ["KAVACH_OIDC_ISSUER"] = _orig_oidc_issuer
        elif "KAVACH_OIDC_ISSUER" in os.environ:
            del os.environ["KAVACH_OIDC_ISSUER"]


def test_keycloak_service_token() -> None:
    """Keycloak mode should validate a real service account token."""
    print("[test_keycloak_service_token]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    issuer = os.getenv("KAVACH_OIDC_ISSUER")

    # Clear cached dependencies
    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    # Fetch a real token from Keycloak
    token_data = _get_keycloak_token()
    access_token = token_data["access_token"]

    service = AuthenticationService(issuer=issuer, jwks_refresh_seconds=300)
    principal = service.validate(access_token)

    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.principal_type.value == "SERVICE"
    assert principal.client_id == "kavach-service"
    assert principal.issuer == issuer
    print(f"  subject={principal.subject}")
    print(f"  principal_type={principal.principal_type.value}")
    print(f"  client_id={principal.client_id}")
    print(f"  organization_id={principal.organization_id}")
    print("  PASSED")


def test_keycloak_full_pipeline() -> None:
    """Full pipeline: JWT → AuthenticatedPrincipal → TenantContext."""
    print("[test_keycloak_full_pipeline]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    issuer = os.getenv("KAVACH_OIDC_ISSUER")

    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    token_data = _get_keycloak_token()
    access_token = token_data["access_token"]

    service = AuthenticationService(issuer=issuer, jwks_refresh_seconds=300)
    principal = service.validate(access_token)

    factory = TenantContextFactory()
    ctx = factory.create(principal, correlation_id="smoke-corr-123")

    assert ctx.actor_id == principal.subject
    assert ctx.correlation_id == "smoke-corr-123"
    print(f"  actor_id={ctx.actor_id}")
    print(f"  organization_id={ctx.organization_id}")
    print(f"  request_id={ctx.request_id}")
    print(f"  correlation_id={ctx.correlation_id}")
    print("  PASSED")


def test_keycloak_fastapi_dependency() -> None:
    """FastAPI dependency should return principal from Bearer token."""
    print("[test_keycloak_fastapi_dependency]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    from kavach.api.dependencies.authentication import get_authenticated_principal

    token_data = _get_keycloak_token()
    access_token = token_data["access_token"]

    class FakeRequest:
        pass

    principal = get_authenticated_principal(
        authorization=f"Bearer {access_token}", request=FakeRequest()
    )

    assert isinstance(principal, AuthenticatedPrincipal)
    assert principal.principal_type.value == "SERVICE"
    print(f"  subject={principal.subject}")
    print("  PASSED")


def test_missing_authorization_header() -> None:
    """Missing Authorization header should return 401."""
    print("[test_missing_authorization_header]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    from fastapi import HTTPException
    from kavach.api.dependencies.authentication import get_authenticated_principal

    class FakeRequest:
        pass

    try:
        get_authenticated_principal(authorization=None, request=FakeRequest())
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["error"]["code"] == "missing_authorization"
        print(f"  status={exc.status_code}")
        print(f"  code={exc.detail['error']['code']}")
        print("  PASSED")


def test_invalid_bearer_scheme() -> None:
    """Non-Bearer Authorization scheme should return 401."""
    print("[test_invalid_bearer_scheme]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    from fastapi import HTTPException
    from kavach.api.dependencies.authentication import get_authenticated_principal

    class FakeRequest:
        pass

    try:
        get_authenticated_principal(
            authorization="Basic dXNlcjpwYXNz", request=FakeRequest()
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["error"]["code"] == "invalid_authorization"
        print(f"  status={exc.status_code}")
        print(f"  code={exc.detail['error']['code']}")
        print("  PASSED")


def test_expired_token() -> None:
    """Expired JWT should return 401 with token_expired code."""
    print("[test_expired_token]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    from fastapi import HTTPException
    from kavach.api.dependencies.authentication import get_authenticated_principal

    class FakeRequest:
        pass

    expired_token = _make_fake_jwt(exp=int(time.time()) - 3600)

    try:
        get_authenticated_principal(
            authorization=f"Bearer {expired_token}", request=FakeRequest()
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["error"]["code"] == "token_expired"
        print(f"  status={exc.status_code}")
        print(f"  code={exc.detail['error']['code']}")
        print("  PASSED")


def test_invalid_issuer() -> None:
    """JWT with wrong issuer should return 401 with invalid_issuer code."""
    print("[test_invalid_issuer]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    from fastapi import HTTPException
    from kavach.api.dependencies.authentication import get_authenticated_principal

    class FakeRequest:
        pass

    wrong_issuer_token = _make_fake_jwt(iss="http://evil.com/realms/kavach")

    try:
        get_authenticated_principal(
            authorization=f"Bearer {wrong_issuer_token}", request=FakeRequest()
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["error"]["code"] == "invalid_issuer"
        print(f"  status={exc.status_code}")
        print(f"  code={exc.detail['error']['code']}")
        print("  PASSED")


def test_malformed_token() -> None:
    """Malformed JWT should return 401 with malformed_token code."""
    print("[test_malformed_token]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    from fastapi import HTTPException
    from kavach.api.dependencies.authentication import get_authenticated_principal

    class FakeRequest:
        pass

    try:
        get_authenticated_principal(
            authorization="Bearer not-a-real-token", request=FakeRequest()
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["error"]["code"] == "malformed_token"
        print(f"  status={exc.status_code}")
        print(f"  code={exc.detail['error']['code']}")
        print("  PASSED")


def test_unsupported_algorithm() -> None:
    """JWT with unsupported algorithm should return 401."""
    print("[test_unsupported_algorithm]")

    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    if auth_mode != "keycloak":
        print("  SKIPPED (KAVACH_AUTH_MODE != keycloak)")
        return

    import kavach.api.dependencies.authentication as auth_mod
    auth_mod.get_authentication_service.cache_clear()

    from fastapi import HTTPException
    from kavach.api.dependencies.authentication import get_authenticated_principal

    class FakeRequest:
        pass

    hs256_token = _make_fake_jwt(alg="HS256")

    try:
        get_authenticated_principal(
            authorization=f"Bearer {hs256_token}", request=FakeRequest()
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["error"]["code"] == "unsupported_algorithm"
        print(f"  status={exc.status_code}")
        print(f"  code={exc.detail['error']['code']}")
        print("  PASSED")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    auth_mode = os.getenv("KAVACH_AUTH_MODE")
    print(f"Auth mode: {auth_mode}")
    if auth_mode == "keycloak":
        print(f"OIDC issuer: {os.getenv('KAVACH_OIDC_ISSUER')}")
    print()

    passed = 0
    failed = 0
    skipped = 0

    tests = [
        test_development_mode,
        test_keycloak_service_token,
        test_keycloak_full_pipeline,
        test_keycloak_fastapi_dependency,
        test_missing_authorization_header,
        test_invalid_bearer_scheme,
        test_expired_token,
        test_invalid_issuer,
        test_malformed_token,
        test_unsupported_algorithm,
    ]

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as exc:
            print(f"  FAILED: {exc}")
            failed += 1
        except Exception as exc:
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
