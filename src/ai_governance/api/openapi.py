"""Canonical OpenAPI visibility metadata and public-reference generation.

The FastAPI application remains the source of truth for every REST operation.
This module only annotates those operations with an OpenAPI extension and
derives the externally published contract from that document.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from jsonschema import Draft202012Validator
from openapi_spec_validator import OpenAPIV31SpecValidator

VISIBILITY_EXTENSION = "x-ai-governance-visibility"
"""OpenAPI extension that classifies a REST operation for publication."""

BEARER_AUTH_SCHEME_NAME = "BearerAuth"
"""Canonical OpenAPI security-scheme identifier for operator requests."""

_OPENAPI_METHODS = frozenset(
    {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
)
_PUBLIC_VISIBILITIES = frozenset({"public", "operator"})
_INTERNAL_HOST_MARKERS = ("docker", ".internal", ".local", "localhost.localdomain")
_REFERENCE_PATH = Path("generated/openapi/ai-governance-v1.json")
_DEVELOPMENT_ONLY_HEADERS = frozenset({"x-ai-governance-actor-id"})


class ApiVisibility(StrEnum):
    """Publication audience for one REST operation."""

    PUBLIC = "public"
    OPERATOR = "operator"
    INTERNAL = "internal"


def mark_router_visibility(router: APIRouter, visibility: ApiVisibility) -> None:
    """Attach visibility to every concrete operation owned by ``router``.

    The extension is added to ``APIRoute.openapi_extra`` before FastAPI copies
    routes into the application. It is therefore part of the canonical OpenAPI
    document, rather than a separate documentation allow-list.
    """

    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        openapi_extra = dict(route.openapi_extra or {})
        existing = openapi_extra.get(VISIBILITY_EXTENSION)
        if existing is not None and existing != visibility.value:
            raise ValueError(
                f"Route {route.path!r} has conflicting OpenAPI visibility metadata."
            )
        openapi_extra[VISIBILITY_EXTENSION] = visibility.value
        if visibility == ApiVisibility.OPERATOR:
            openapi_extra.setdefault("security", [{BEARER_AUTH_SCHEME_NAME: []}])
        route.openapi_extra = openapi_extra


def install_openapi_security_scheme(app: FastAPI) -> None:
    """Expose the API's existing bearer authentication contract in OpenAPI."""

    default_openapi = app.openapi

    def documented_openapi() -> dict[str, Any]:
        spec = default_openapi()
        components = spec.setdefault("components", {})
        schemes = components.setdefault("securitySchemes", {})
        schemes.setdefault(
            BEARER_AUTH_SCHEME_NAME,
            {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Keycloak access token for an operator or integration.",
            },
        )
        return spec

    app.openapi = documented_openapi  # type: ignore[method-assign]


def build_public_openapi_spec(
    canonical_spec: Mapping[str, Any],
    *,
    production_server_url: str | None = None,
    local_server_url: str | None = None,
) -> dict[str, Any]:
    """Return the deterministic public reference derived from FastAPI OpenAPI.

    Only ``PUBLIC`` and ``OPERATOR`` operations are retained. Missing or
    malformed visibility is deliberately treated as ``INTERNAL``.
    """

    spec = copy.deepcopy(dict(canonical_spec))
    public_paths, tag_visibility = _published_paths(spec.get("paths", {}))
    spec["paths"] = public_paths
    _prune_components(spec)
    _configure_reference_metadata(spec, tag_visibility)
    spec["servers"] = _reference_servers(
        production_server_url=production_server_url,
        local_server_url=local_server_url,
    )
    return spec


def generate_public_openapi_spec(
    *,
    production_server_url: str | None = None,
    local_server_url: str | None = None,
) -> dict[str, Any]:
    """Generate a public contract from a freshly constructed REST application."""

    # Import lazily to avoid an application/module import cycle.
    from ai_governance.api.app import create_app

    return build_public_openapi_spec(
        create_app().openapi(),
        production_server_url=production_server_url,
        local_server_url=local_server_url,
    )


def validate_public_openapi_spec(spec: Mapping[str, Any]) -> None:
    """Validate publication invariants, JSON Schema components, and references."""

    if not str(spec.get("openapi", "")).startswith("3.1."):
        raise ValueError("The generated reference must be an OpenAPI 3.1 document.")
    if not isinstance(spec.get("info"), Mapping):
        raise TypeError("The generated reference is missing OpenAPI info metadata.")
    if not isinstance(spec.get("paths"), Mapping) or not spec["paths"]:
        raise ValueError("The generated reference does not contain published operations.")

    _assert_reference_resolution(spec)
    _assert_component_schemas_are_valid(spec)
    _assert_safe_servers(spec)
    OpenAPIV31SpecValidator(spec).validate()

    for path, path_item in spec["paths"].items():
        if not isinstance(path_item, Mapping):
            raise TypeError(f"OpenAPI path {path!r} is not an object.")
        for method, operation in path_item.items():
            if method.lower() not in _OPENAPI_METHODS:
                continue
            if not isinstance(operation, Mapping):
                raise TypeError(f"OpenAPI operation {method.upper()} {path} is not an object.")
            visibility = operation.get(VISIBILITY_EXTENSION, ApiVisibility.INTERNAL)
            if visibility not in _PUBLIC_VISIBILITIES:
                raise ValueError(f"Internal operation {method.upper()} {path} was published.")


def write_public_openapi_spec(path: Path | None = None) -> Path:
    """Generate, validate, and write the static API-reference source document."""

    destination = path or reference_spec_path()
    spec = generate_public_openapi_spec()
    validate_public_openapi_spec(spec)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_serialized_spec(spec), encoding="utf-8")
    return destination


def check_public_openapi_spec(path: Path | None = None) -> Path:
    """Fail when the checked-in reference does not match current REST contracts."""

    destination = path or reference_spec_path()
    if not destination.is_file():
        raise ValueError(
            f"Generated API reference is missing: {destination}. "
            "Run `uv run python -m ai_governance.api.openapi generate`."
        )
    expected = generate_public_openapi_spec()
    validate_public_openapi_spec(expected)
    actual = json.loads(destination.read_text(encoding="utf-8"))
    validate_public_openapi_spec(actual)
    if _serialized_spec(actual) != _serialized_spec(expected):
        raise ValueError(
            "Generated API reference is stale. "
            "Run `uv run python -m ai_governance.api.openapi generate`."
        )
    return destination


def reference_spec_path() -> Path:
    """Return the checked-in public contract generated from FastAPI routes."""

    return Path(__file__).resolve().parents[3] / _REFERENCE_PATH


def _published_paths(
    paths: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, set[str]]]:
    published: dict[str, Any] = {}
    tag_visibility: dict[str, set[str]] = {}
    for path, raw_path_item in paths.items():
        if not isinstance(raw_path_item, Mapping):
            continue
        path_item = {
            key: copy.deepcopy(value)
            for key, value in raw_path_item.items()
            if key.lower() not in _OPENAPI_METHODS
        }
        for method, raw_operation in raw_path_item.items():
            if method.lower() not in _OPENAPI_METHODS or not isinstance(raw_operation, Mapping):
                continue
            visibility = raw_operation.get(VISIBILITY_EXTENSION, ApiVisibility.INTERNAL)
            if visibility not in _PUBLIC_VISIBILITIES:
                continue
            operation = copy.deepcopy(dict(raw_operation))
            _remove_development_only_parameters(operation)
            path_item[method] = operation
            for tag in operation.get("tags", []):
                tag_visibility.setdefault(str(tag), set()).add(str(visibility))
        if any(key.lower() in _OPENAPI_METHODS for key in path_item):
            published[path] = path_item
    return published, tag_visibility


def _remove_development_only_parameters(operation: dict[str, Any]) -> None:
    """Do not advertise development-only identity injection to integrators."""

    parameters = operation.get("parameters")
    if not isinstance(parameters, list):
        return
    operation["parameters"] = [
        parameter
        for parameter in parameters
        if not (
            isinstance(parameter, Mapping)
            and parameter.get("in") == "header"
            and str(parameter.get("name", "")).lower() in _DEVELOPMENT_ONLY_HEADERS
        )
    ]


def _prune_components(spec: dict[str, Any]) -> None:
    components = spec.get("components")
    if not isinstance(components, Mapping):
        return

    referenced = _component_references(spec.get("paths", {})) | _security_scheme_references(
        spec.get("paths", {})
    )
    retained: dict[str, dict[str, Any]] = {}
    pending = list(referenced)
    while pending:
        section, name = pending.pop()
        if name in retained.get(section, {}):
            continue
        source_section = components.get(section)
        if not isinstance(source_section, Mapping) or name not in source_section:
            raise ValueError(f"OpenAPI reference points to missing component {section}/{name}.")
        value = copy.deepcopy(source_section[name])
        retained.setdefault(section, {})[name] = value
        pending.extend(_component_references(value))

    spec["components"] = {
        section: {name: values[name] for name in sorted(values)}
        for section, values in sorted(retained.items())
    }


def _configure_reference_metadata(
    spec: dict[str, Any], tag_visibility: Mapping[str, set[str]]
) -> None:
    info = dict(spec.get("info", {}))
    info["title"] = "AI Governance Control Plane API Reference"
    source_description = str(info.get("description", "")).strip()
    info["description"] = (
        f"{source_description}\n\n" if source_description else ""
    ) + (
        "## Authentication\n\n"
        "Operator endpoints require `Authorization: Bearer <token>`. Tenant-scoped "
        "requests also use `X-AI-Governance-Organization-Id` and, where applicable, "
        "`X-AI-Governance-Project-Id`. Tokens entered into this reference are kept only "
        "for the current browser session."
    )
    spec["info"] = info

    security_schemes = spec.setdefault("components", {}).get("securitySchemes", {})
    if BEARER_AUTH_SCHEME_NAME not in security_schemes:
        raise ValueError("The canonical OpenAPI document is missing BearerAuth.")
    spec["tags"] = [
        {
            "name": tag,
            "description": (
                "Public integration endpoints."
                if visibility == {ApiVisibility.PUBLIC}
                else "Authenticated operator endpoints."
            ),
        }
        for tag, visibility in sorted(tag_visibility.items())
    ]
    public_tags = sorted(
        tag for tag, visibility in tag_visibility.items() if visibility == {ApiVisibility.PUBLIC}
    )
    operator_tags = sorted(
        tag for tag, visibility in tag_visibility.items() if ApiVisibility.OPERATOR in visibility
    )
    spec["x-tagGroups"] = [
        group
        for group in (
            {"name": "Public APIs", "tags": public_tags},
            {"name": "Operator APIs", "tags": operator_tags},
        )
        if group["tags"]
    ]


def _reference_servers(
    *, production_server_url: str | None, local_server_url: str | None
) -> list[dict[str, str]]:
    production_url = production_server_url or os.getenv(
        "AI_GOVERNANCE_PUBLIC_API_URL", "https://governance.bhanuj.ai"
    )
    local_url = local_server_url or os.getenv(
        "AI_GOVERNANCE_LOCAL_API_URL", "http://localhost:8000"
    )
    return [
        {"url": _safe_server_url(production_url, allow_localhost=False), "description": "Production"},
        {"url": _safe_server_url(local_url, allow_localhost=True), "description": "Local"},
    ]


def _safe_server_url(value: str, *, allow_localhost: bool) -> str:
    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname or parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"Invalid public API server URL: {value!r}")
    if hostname == "localhost" and allow_localhost:
        return value.rstrip("/")
    if parsed.scheme != "https" or hostname == "localhost" or any(
        marker in hostname for marker in _INTERNAL_HOST_MARKERS
    ):
        raise ValueError(f"Unsafe public API server URL: {value!r}")
    return value.rstrip("/")


def _component_references(value: Any) -> set[tuple[str, str]]:
    references: set[tuple[str, str]] = set()
    for reference in _references(value):
        match = re.fullmatch(r"#/components/([^/]+)/([^/]+)", reference)
        if match:
            references.add((match.group(1), match.group(2)))
    return references


def _security_scheme_references(value: Any) -> set[tuple[str, str]]:
    references: set[tuple[str, str]] = set()
    if isinstance(value, Mapping):
        security = value.get("security")
        if isinstance(security, list):
            for requirement in security:
                if isinstance(requirement, Mapping):
                    references.update(
                        ("securitySchemes", str(name)) for name in requirement
                    )
        for nested in value.values():
            references.update(_security_scheme_references(nested))
    elif isinstance(value, list):
        for nested in value:
            references.update(_security_scheme_references(nested))
    return references


def _references(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        reference = value.get("$ref")
        if isinstance(reference, str):
            yield reference
        for nested in value.values():
            yield from _references(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _references(nested)


def _assert_reference_resolution(spec: Mapping[str, Any]) -> None:
    for reference in _references(spec):
        if not reference.startswith("#/"):
            continue
        current: Any = spec
        for token in reference[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, Mapping) or token not in current:
                raise ValueError(f"OpenAPI reference does not resolve: {reference}")
            current = current[token]


def _assert_component_schemas_are_valid(spec: Mapping[str, Any]) -> None:
    components = spec.get("components", {})
    schemas = components.get("schemas", {}) if isinstance(components, Mapping) else {}
    if not isinstance(schemas, Mapping):
        raise TypeError("OpenAPI components.schemas is not an object.")
    for name, schema in schemas.items():
        if not isinstance(schema, Mapping):
            raise TypeError(f"OpenAPI schema {name!r} is not an object.")
        Draft202012Validator.check_schema(schema)


def _assert_safe_servers(spec: Mapping[str, Any]) -> None:
    servers = spec.get("servers")
    if not isinstance(servers, list) or not servers:
        raise ValueError("The generated reference has no server selection.")
    for server in servers:
        if not isinstance(server, Mapping) or not isinstance(server.get("url"), str):
            raise TypeError("The generated reference has an invalid server entry.")
        _safe_server_url(server["url"], allow_localhost=server.get("description") == "Local")


def _serialized_spec(spec: Mapping[str, Any]) -> str:
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the public AI Governance OpenAPI reference.")
    parser.add_argument("command", choices=("generate", "check"))
    args = parser.parse_args()
    path = write_public_openapi_spec() if args.command == "generate" else check_public_openapi_spec()
    print(path)


if __name__ == "__main__":
    main()
