"""
Keycloak OIDC authentication service.

Validates JWT access tokens issued by Keycloak, retrieves and caches
signing keys from the JWKS endpoint, and builds an immutable
AuthenticatedPrincipal from validated claims.

This module implements the authentication plane only. It never makes
authorization decisions, resolves memberships, or touches the RBAC model.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .domain import ActorType, AuthenticatedPrincipal

logger = logging.getLogger("ai_governance.tenancy.authentication")


class AuthenticationError(Exception):
    """Raised when JWT validation fails."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code or "authentication_error"
        super().__init__(message)


@dataclass(frozen=True)
class _Jwk:
    """Parsed JSON Web Key."""

    kid: str
    n: str
    e: str


class _JwksCache:
    """In-memory cache for Keycloak JWKS signing keys."""

    def __init__(self, refresh_seconds: int = 300) -> None:
        self._refresh_seconds = refresh_seconds
        self._keys: dict[str, _Jwk] = {}
        self._fetched_at: float = 0.0

    def is_expired(self) -> bool:
        return (time.monotonic() - self._fetched_at) >= self._refresh_seconds

    def get(self, kid: str | None) -> _Jwk | None:
        if not kid:
            return None
        return self._keys.get(kid)

    def set_from_jwks(self, jwks: dict[str, Any]) -> None:
        self._keys = {}
        for key in jwks.get("keys", []):
            kid = key.get("kid")
            n = key.get("n")
            e = key.get("e")
            if kid and n and e:
                self._keys[kid] = _Jwk(kid=kid, n=n, e=e)
        self._fetched_at = time.monotonic()


def _base64url_decode(value: str) -> bytes:
    """Decode a base64url-encoded string with padding restoration."""
    padding = 4 - len(value) % 4
    if padding != 4:
        value += "=" * padding
    return base64.urlsafe_b64decode(value)


def _rsa_public_key_from_jwk(jwk: _Jwk) -> Any:
    """Construct an RSA public key from a JWK (n, e) using cryptography.

    Per RFC 7518 Section 6.3.1.1, the RSA modulus (n) and exponent (e)
    are base64url-encoded.  We decode them to big-endian byte strings
    before constructing the RSA public key.
    """
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric.rsa import (
        RSAPublicNumbers,
    )

    # Decode base64url-encoded n and e to byte strings
    n_bytes = _base64url_decode(jwk.n)
    e_bytes = _base64url_decode(jwk.e)

    # Convert byte strings to integers (big-endian)
    n = int.from_bytes(n_bytes, byteorder='big')
    e = int.from_bytes(e_bytes, byteorder='big')

    public_numbers = RSAPublicNumbers(e, n)
    return public_numbers.public_key(default_backend())


class AuthenticationService:
    """
    Validate JWT access tokens from Keycloak.

    Responsibilities
    ----------------
    - Retrieve and cache JWKS signing keys
    - Validate JWT signature, issuer, and expiry
    - Build AuthenticatedPrincipal from validated claims

    Never
    -----
    - Authorize requests
    - Resolve memberships or permissions
    - Touch the RBAC model
    """

    def __init__(
        self,
        issuer: str,
        jwks_refresh_seconds: int = 300,
        audience: str | None = None,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._jwks_url = f"{self._issuer}/protocol/openid-connect/certs"
        self._cache = _JwksCache(jwks_refresh_seconds)
        self._audience = audience

    def _fetch_jwks(self) -> dict[str, Any]:
        """Download JWKS from Keycloak."""
        try:
            with urlopen(self._jwks_url, timeout=10.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            logger.error(
                "jwks_fetch_failed",
                extra={"status_code": exc.code, "url": self._jwks_url},
            )
            raise AuthenticationError(
                "Unable to retrieve signing keys from Keycloak",
                code="jwks_fetch_failed",
            ) from exc
        except URLError as exc:
            logger.error(
                "jwks_fetch_failed",
                extra={"url": self._jwks_url, "reason": str(exc.reason)},
            )
            raise AuthenticationError(
                "Unable to retrieve signing keys from Keycloak",
                code="jwks_fetch_failed",
            ) from exc

    def _resolve_key(self, header: dict[str, Any]) -> _Jwk | None:
        """Find the matching signing key by kid."""
        kid = header.get("kid")
        key = self._cache.get(kid)
        if key is not None:
            return key

        # Cache miss — refresh JWKS
        jwks = self._fetch_jwks()
        self._cache.set_from_jwks(jwks)
        return self._cache.get(kid)

    def validate(self, token: str) -> AuthenticatedPrincipal:
        """
        Validate a JWT access token and return an AuthenticatedPrincipal.

        Validates
        ---------
        - Signature (RS256 via JWKS)
        - Issuer (matches configured issuer)
        - Expiry (not expired)

        Rejects
        -------
        - Invalid signature → AuthenticationError
        - Expired token → AuthenticationError
        - Mismatched issuer → AuthenticationError
        - Malformed token → AuthenticationError
        """
        try:
            parts = token.split(".")
            if len(parts) != 3:
                raise AuthenticationError(
                    "Malformed JWT: expected three dot-separated segments",
                    code="malformed_token",
                )

            # Decode header and payload without verification
            header_raw = _base64url_decode(parts[0])
            payload_raw = _base64url_decode(parts[1])

            header = json.loads(header_raw)
            payload = json.loads(payload_raw)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(
                "Malformed JWT: unable to decode token",
                code="malformed_token",
            ) from exc

        # Validate algorithm
        alg = header.get("alg")
        if alg != "RS256":
            raise AuthenticationError(
                f"Unsupported JWT algorithm: {alg}",
                code="unsupported_algorithm",
            )

        # Validate issuer
        token_issuer = payload.get("iss")
        if token_issuer != self._issuer:
            raise AuthenticationError(
                f"JWT issuer mismatch: expected {self._issuer}, got {token_issuer}",
                code="invalid_issuer",
            )

        # Validate expiry
        exp = payload.get("exp")
        if not isinstance(exp, (int, float)) or isinstance(exp, bool):
            raise AuthenticationError(
                "JWT missing expiry claim",
                code="missing_claims",
            )
        import time as _time

        if _time.time() > exp:
            raise AuthenticationError(
                "JWT has expired",
                code="token_expired",
            )

        if self._audience and not _has_audience(payload.get("aud"), self._audience):
            raise AuthenticationError(
                f"JWT audience does not include {self._audience}",
                code="invalid_audience",
            )

        # Resolve signing key and verify signature
        jwk = self._resolve_key(header)
        if jwk is None:
            raise AuthenticationError(
                "Unable to resolve signing key for JWT",
                code="key_resolution_failed",
            )

        # Build signature input and verify
        try:
            signature = _base64url_decode(parts[2])
            signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")

            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding

            public_key = _rsa_public_key_from_jwk(jwk)
            public_key.verify(
                signature,
                signing_input,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception:
            raise AuthenticationError(
                "JWT signature verification failed",
                code="invalid_signature",
            )

        # Build principal from validated claims
        subject = payload.get("sub")
        if not subject:
            logger.warning(
                "jwt_missing_subject_claim: issuer=%s azp=%s claims=%s",
                token_issuer,
                payload.get("azp"),
                sorted(payload),
            )
            raise AuthenticationError(
                "JWT missing subject claim",
                code="missing_claims",
            )

        # Map principal_type from JWT claim or default to USER
        raw_type = payload.get("principal_type", "USER").upper()
        if raw_type == "SERVICE":
            principal_type = ActorType.SERVICE
        elif raw_type == "SYSTEM":
            principal_type = ActorType.SYSTEM
        else:
            principal_type = ActorType.USER

        client_id = payload.get("azp") or payload.get("client_id", "")
        organization_id = payload.get("organization_id")

        logger.info(
            "jwt_authenticated",
            extra={
                "subject": subject,
                "client_id": client_id,
                "issuer": token_issuer,
                "principal_type": principal_type.value,
            },
        )

        return AuthenticatedPrincipal(
            subject=subject,
            principal_type=principal_type,
            organization_id=organization_id,
            client_id=client_id,
            issuer=token_issuer,
        )


def _has_audience(value: Any, expected: str) -> bool:
    """Return whether a JWT ``aud`` claim names the expected resource."""
    if isinstance(value, str):
        return value == expected
    return isinstance(value, list) and expected in value
