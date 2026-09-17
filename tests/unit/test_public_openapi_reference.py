from __future__ import annotations

import json

import pytest

from ai_governance.api.app import create_app
from ai_governance.api.openapi import (
    VISIBILITY_EXTENSION,
    ApiVisibility,
    _serialized_spec,
    build_public_openapi_spec,
    check_public_openapi_spec,
    reference_spec_path,
    validate_public_openapi_spec,
)


def _canonical_spec() -> dict:
    return create_app().openapi()


def test_visibility_is_emitted_by_the_canonical_openapi_contract() -> None:
    spec = _canonical_spec()

    assert (
        spec["paths"]["/api/v1/providers"]["get"][VISIBILITY_EXTENSION]
        == ApiVisibility.PUBLIC
    )
    assert (
        spec["paths"]["/api/v1/local/demo/seed"]["post"][VISIBILITY_EXTENSION]
        == ApiVisibility.INTERNAL
    )
    assert spec["paths"]["/health"]["get"][VISIBILITY_EXTENSION] == ApiVisibility.INTERNAL


def test_public_reference_contains_supported_operations_and_excludes_internal_routes() -> None:
    spec = build_public_openapi_spec(_canonical_spec())

    assert "/api/v1/providers" in spec["paths"]
    assert "/api/v1/decisions" in spec["paths"]
    assert "/health" not in spec["paths"]
    assert "/ready" not in spec["paths"]
    assert "/api/v1/local/demo/seed" not in spec["paths"]
    assert "/api/v1/runtime/extensions" not in spec["paths"]
    assert "/api/v1/telemetry/status" not in spec["paths"]
    assert all(
        operation[VISIBILITY_EXTENSION] in {ApiVisibility.PUBLIC, ApiVisibility.OPERATOR}
        for path_item in spec["paths"].values()
        for method, operation in path_item.items()
        if method.lower() in {"delete", "get", "patch", "post", "put"}
    )


def test_unclassified_operations_default_to_internal() -> None:
    canonical = _canonical_spec()
    canonical["paths"]["/unclassified"] = {
        "get": {"responses": {"200": {"description": "not published"}}}
    }

    spec = build_public_openapi_spec(canonical)

    assert "/unclassified" not in spec["paths"]


def test_public_reference_is_deterministic_and_formally_valid() -> None:
    first = build_public_openapi_spec(_canonical_spec())
    second = build_public_openapi_spec(_canonical_spec())

    assert _serialized_spec(first) == _serialized_spec(second)
    validate_public_openapi_spec(first)


def test_public_reference_preserves_bearer_auth_and_safe_server_selection() -> None:
    spec = build_public_openapi_spec(_canonical_spec())

    assert spec["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Keycloak access token for an operator or integration.",
    }
    assert spec["paths"]["/api/v1/decisions"]["get"]["security"] == [
        {"BearerAuth": []}
    ]
    decision_headers = {
        parameter["name"]
        for parameter in spec["paths"]["/api/v1/decisions"]["get"]["parameters"]
        if parameter.get("in") == "header"
    }
    assert "X-AI-Governance-Organization-Id" in decision_headers
    assert "X-AI-Governance-Project-Id" in decision_headers
    assert "X-AI-Governance-Actor-Id" not in decision_headers
    assert spec["servers"] == [
        {"url": "https://governance.bhanuj.ai", "description": "Production"},
        {"url": "http://localhost:8000", "description": "Local"},
    ]
    rendered = json.dumps(spec).lower()
    assert "ai-governance-platform" not in rendered
    assert "keycloak.localhost" not in rendered
    assert "seaweedfs" not in rendered
    assert "neo4j" not in rendered


def test_public_reference_rejects_internal_server_urls() -> None:
    with pytest.raises(ValueError, match="Unsafe public API server URL"):
        build_public_openapi_spec(
            _canonical_spec(), production_server_url="http://ai-governance-platform:8000"
        )


def test_checked_in_reference_is_current() -> None:
    assert check_public_openapi_spec() == reference_spec_path()
