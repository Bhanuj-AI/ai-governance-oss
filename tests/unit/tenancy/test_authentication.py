"""
Unit tests for the Keycloak OIDC authentication service.

Tests cover JWT validation, JWKS caching, principal building, and
tenant context factory behaviour.
"""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from kavach.tenancy.authentication import (
    AuthenticationError,
    AuthenticationService,
)
from kavach.tenancy.context_factory import TenantContextFactory
from kavach.tenancy.domain import ActorType, AuthenticatedPrincipal


# ---------------------------------------------------------------------------
# Helpers — build a fake JWT (signature is intentionally invalid; we mock
# the RSA verification path so any signature byte sequence works).
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_jwt(
    sub: str = "user-123",
    iss: str = "http://localhost:8080/realms/kavach",
    exp: int | None = None,
    azp: str = "kavach-service",
    principal_type: str = "USER",
    organization_id: str | None = None,
    kid: str = "key-1",
    alg: str = "RS256",
    aud: str | list[str] | None = None,
) -> str:
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    header_b64 = _b64url_encode(json.dumps(header).encode())

    payload: dict = {
        "sub": sub,
        "iss": iss,
        "azp": azp,
        "principal_type": principal_type,
    }
    # Always include exp unless explicitly set to None
    if exp is not None:
        payload["exp"] = exp
    elif "exp" not in payload:
        payload["exp"] = int(time.time()) + 3600
    if organization_id is not None:
        payload["organization_id"] = organization_id
    if aud is not None:
        payload["aud"] = aud

    payload_b64 = _b64url_encode(json.dumps(payload).encode())
    # Fake signature — will be mocked at the RSA layer
    sig_b64 = _b64url_encode(b"\x00" * 256)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def _make_jwt_no_exp(
    sub: str = "user-123",
    iss: str = "http://localhost:8080/realms/kavach",
    azp: str = "kavach-service",
    principal_type: str = "USER",
    organization_id: str | None = None,
    kid: str = "key-1",
    alg: str = "RS256",
) -> str:
    """Build a JWT without an exp claim to test missing-exp detection."""
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    header_b64 = _b64url_encode(json.dumps(header).encode())

    payload: dict = {
        "sub": sub,
        "iss": iss,
        "azp": azp,
        "principal_type": principal_type,
    }
    # Intentionally omit exp
    if organization_id is not None:
        payload["organization_id"] = organization_id

    payload_b64 = _b64url_encode(json.dumps(payload).encode())
    sig_b64 = _b64url_encode(b"\x00" * 256)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def _make_jwt_no_sub(
    iss: str = "http://localhost:8080/realms/kavach",
    exp: int = None,
    azp: str = "kavach-service",
    principal_type: str = "USER",
    organization_id: str | None = None,
    kid: str = "key-1",
    alg: str = "RS256",
) -> str:
    """Build a JWT without a sub claim (but with valid exp)."""
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    header_b64 = _b64url_encode(json.dumps(header).encode())

    payload: dict = {
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


def _make_mock_urlopen_response(jwks_data: dict) -> MagicMock:
    """Create a properly configured mock for urlopen context manager.

    When used as ``with urlopen(...) as response:``, the mock's __enter__
    must return the actual response object (not another MagicMock).
    """
    resp = MagicMock()
    resp.read.return_value = json.dumps(jwks_data).encode("utf-8")

    # Wire up context manager protocol
    ctx = MagicMock()
    ctx.__enter__.return_value = resp
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Malformed tokens
# ---------------------------------------------------------------------------

class TestMalformedTokens:
    def test_empty_string(self):
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="Malformed JWT"):
            service.validate("")

    def test_two_segments(self):
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="Malformed JWT"):
            service.validate("a.b")

    def test_four_segments(self):
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="Malformed JWT"):
            service.validate("a.b.c.d")

    def test_invalid_base64_header(self):
        header_b64 = _b64url_encode(b"not-json")
        payload_b64 = _b64url_encode(json.dumps({"sub": "x"}).encode())
        sig_b64 = _b64url_encode(b"\x00" * 256)
        token = f"{header_b64}.{payload_b64}.{sig_b64}"

        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="Malformed JWT"):
            service.validate(token)


# ---------------------------------------------------------------------------
# Algorithm validation
# ---------------------------------------------------------------------------

class TestAlgorithmValidation:
    def test_unsupported_algorithm(self):
        token = _make_jwt(alg="HS256")
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="Unsupported JWT algorithm"):
            service.validate(token)


# ---------------------------------------------------------------------------
# Issuer validation
# ---------------------------------------------------------------------------

class TestIssuerValidation:
    def test_wrong_issuer(self):
        token = _make_jwt(iss="http://evil.com/realms/kavach")
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="JWT issuer mismatch"):
            service.validate(token)


# ---------------------------------------------------------------------------
# Expiry validation
# ---------------------------------------------------------------------------

class TestExpiryValidation:
    def test_expired_token(self):
        token = _make_jwt(exp=int(time.time()) - 3600)
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="JWT has expired"):
            service.validate(token)

    def test_missing_exp_claim(self):
        token = _make_jwt_no_exp()
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="JWT missing expiry claim"):
            service.validate(token)


class TestAudienceValidation:
    @patch("kavach.tenancy.authentication._rsa_public_key_from_jwk")
    @patch("kavach.tenancy.authentication.urlopen")
    def test_rejects_token_without_expected_resource_audience(
        self, mock_urlopen, mock_rsa
    ):
        mock_rsa.return_value = MagicMock()
        mock_urlopen.return_value = _make_mock_urlopen_response(
            {"keys": [{"kid": "key-1", "n": "abc", "e": "AQAB"}]}
        )
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach",
            audience="http://localhost:8002/mcp",
        )

        with pytest.raises(AuthenticationError, match="JWT audience does not include"):
            service.validate(_make_jwt(aud="some-other-resource"))

    @patch("kavach.tenancy.authentication._rsa_public_key_from_jwk")
    @patch("kavach.tenancy.authentication.urlopen")
    def test_accepts_expected_resource_in_audience_array(self, mock_urlopen, mock_rsa):
        mock_rsa.return_value = MagicMock()
        mock_urlopen.return_value = _make_mock_urlopen_response(
            {"keys": [{"kid": "key-1", "n": "abc", "e": "AQAB"}]}
        )
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach",
            audience="http://localhost:8002/mcp",
        )

        principal = service.validate(
            _make_jwt(aud=["account", "http://localhost:8002/mcp"])
        )

        assert principal.subject == "user-123"

# ---------------------------------------------------------------------------
# Subject validation
# ---------------------------------------------------------------------------

class TestSubjectValidation:
    @patch("kavach.tenancy.authentication._rsa_public_key_from_jwk")
    @patch("kavach.tenancy.authentication.urlopen")
    def test_missing_subject(self, mock_urlopen, mock_rsa):
        # Must include a valid exp so expiry check passes first
        mock_rsa.return_value = MagicMock()

        mock_response = _make_mock_urlopen_response(
            {"keys": [{"kid": "key-1", "n": "abc", "e": "AQAB"}]}
        )
        mock_urlopen.return_value = mock_response

        token = _make_jwt_no_sub(exp=int(time.time()) + 3600)
        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        with pytest.raises(AuthenticationError, match="JWT missing subject claim"):
            service.validate(token)


# ---------------------------------------------------------------------------
# Successful validation (mocked JWKS + RSA)
# ---------------------------------------------------------------------------

class TestSuccessfulValidation:
    @patch("kavach.tenancy.authentication._rsa_public_key_from_jwk")
    @patch("kavach.tenancy.authentication.urlopen")
    def test_valid_token_returns_principal(self, mock_urlopen, mock_rsa):
        mock_rsa.return_value = MagicMock()

        mock_response = _make_mock_urlopen_response(
            {"keys": [{"kid": "key-1", "n": "abc", "e": "AQAB"}]}
        )
        mock_urlopen.return_value = mock_response

        token = _make_jwt()

        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach",
            jwks_refresh_seconds=300,
        )
        principal = service.validate(token)

        assert principal.subject == "user-123"
        assert principal.principal_type == ActorType.USER
        assert principal.client_id == "kavach-service"
        assert principal.issuer == "http://localhost:8080/realms/kavach"
        assert principal.organization_id is None

    @patch("kavach.tenancy.authentication._rsa_public_key_from_jwk")
    @patch("kavach.tenancy.authentication.urlopen")
    def test_service_principal_type(self, mock_urlopen, mock_rsa):
        mock_rsa.return_value = MagicMock()

        mock_response = _make_mock_urlopen_response(
            {"keys": [{"kid": "key-1", "n": "abc", "e": "AQAB"}]}
        )
        mock_urlopen.return_value = mock_response

        token = _make_jwt(principal_type="SERVICE")

        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        principal = service.validate(token)

        assert principal.principal_type == ActorType.SERVICE

    @patch("kavach.tenancy.authentication._rsa_public_key_from_jwk")
    @patch("kavach.tenancy.authentication.urlopen")
    def test_organization_id_from_jwt(self, mock_urlopen, mock_rsa):
        mock_rsa.return_value = MagicMock()

        mock_response = _make_mock_urlopen_response(
            {"keys": [{"kid": "key-1", "n": "abc", "e": "AQAB"}]}
        )
        mock_urlopen.return_value = mock_response

        token = _make_jwt(organization_id="org_test")

        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        principal = service.validate(token)

        assert principal.organization_id == "org_test"

    @patch("kavach.tenancy.authentication._rsa_public_key_from_jwk")
    @patch("kavach.tenancy.authentication.urlopen")
    def test_client_id_falls_back_to_client_id_claim(self, mock_urlopen, mock_rsa):
        mock_rsa.return_value = MagicMock()

        mock_response = _make_mock_urlopen_response(
            {"keys": [{"kid": "key-1", "n": "abc", "e": "AQAB"}]}
        )
        mock_urlopen.return_value = mock_response

        # Build token with client_id instead of azp
        header = {"alg": "RS256", "typ": "JWT", "kid": "key-1"}
        header_b64 = _b64url_encode(json.dumps(header).encode())
        payload = {
            "sub": "user-123",
            "iss": "http://localhost:8080/realms/kavach",
            "principal_type": "USER",
            "exp": int(time.time()) + 3600,
            "client_id": "fallback-client",
        }
        payload_b64 = _b64url_encode(json.dumps(payload).encode())
        sig_b64 = _b64url_encode(b"\x00" * 256)
        token = f"{header_b64}.{payload_b64}.{sig_b64}"

        service = AuthenticationService(
            issuer="http://localhost:8080/realms/kavach"
        )
        principal = service.validate(token)

        assert principal.client_id == "fallback-client"


# ---------------------------------------------------------------------------
# JWKS caching
# ---------------------------------------------------------------------------

class TestJwksCaching:
    @patch("kavach.tenancy.authentication.urlopen")
    def test_jwks_fetched_once_then_cached(self, mock_urlopen):
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_mock_urlopen_response(
                {"keys": [{"kid": "key-1", "n": "abc", "e": "AQAB"}]}
            )

        mock_urlopen.side_effect = side_effect

        with patch("kavach.tenancy.authentication._rsa_public_key_from_jwk") as mock_rsa:
            mock_rsa.return_value = MagicMock()

            token = _make_jwt(exp=int(time.time()) + 3600)

            service = AuthenticationService(
                issuer="http://localhost:8080/realms/kavach",
                jwks_refresh_seconds=300,
            )

            # First call — fetches JWKS
            service.validate(token)
            assert call_count == 1

            # Second call — uses cache
            service.validate(token)
            assert call_count == 1  # Still 1, JWKS was cached


# ---------------------------------------------------------------------------
# TenantContextFactory
# ---------------------------------------------------------------------------

class TestTenantContextFactory:
    def test_creates_context_from_principal(self):
        principal = AuthenticatedPrincipal(
            subject="user-456",
            principal_type=ActorType.USER,
            organization_id="org_test",
            client_id="kavach-service",
            issuer="http://localhost:8080/realms/kavach",
        )

        factory = TenantContextFactory()
        ctx = factory.create(principal)

        assert ctx.actor_id == "user-456"
        assert ctx.organization_id == "org_test"
        assert ctx.project_id is None
        assert ctx.request_id.startswith("req_")
        assert ctx.correlation_id is None

    def test_preserves_correlation_id(self):
        principal = AuthenticatedPrincipal(
            subject="user-789",
            principal_type=ActorType.SERVICE,
            organization_id=None,
            client_id="svc-client",
            issuer="http://localhost:8080/realms/kavach",
        )

        factory = TenantContextFactory()
        ctx = factory.create(principal, correlation_id="corr-123")

        assert ctx.correlation_id == "corr-123"

    def test_preserves_request_id(self):
        principal = AuthenticatedPrincipal(
            subject="user-789",
            principal_type=ActorType.SERVICE,
            organization_id=None,
            client_id="svc-client",
            issuer="http://localhost:8080/realms/kavach",
        )

        factory = TenantContextFactory()
        ctx = factory.create(principal, request_id="custom-req-id")

        assert ctx.request_id == "custom-req-id"

    def test_null_organization_becomes_empty_string(self):
        principal = AuthenticatedPrincipal(
            subject="user-000",
            principal_type=ActorType.USER,
            organization_id=None,
            client_id="client",
            issuer="http://localhost:8080/realms/kavach",
        )

        factory = TenantContextFactory()
        ctx = factory.create(principal)

        assert ctx.organization_id == ""

    def test_explicit_organization_and_project_override_principal(self):
        principal = AuthenticatedPrincipal(
            subject="user-123",
            principal_type=ActorType.USER,
            organization_id="jwt-org",
            client_id="client",
            issuer="http://localhost:8080/realms/kavach",
        )

        context = TenantContextFactory().create(
            principal,
            organization_id="header-org",
            project_id="project-1",
            request_id="request-1",
        )

        assert context.organization_id == "header-org"
        assert context.project_id == "project-1"
        assert context.request_id == "request-1"
