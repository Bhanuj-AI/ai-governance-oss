"""Discover provider model identifiers through a tenant runtime connection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ai_governance.domain.models import runtime_model_provider_key
from ai_governance.services.runtime_connection_service import RuntimeConnectionService
from ai_governance.tenancy.domain import TenantContext

LOGGER = logging.getLogger(__name__)


class ModelCatalogDiscoveryError(Exception):
    """Raised when a runtime provider cannot safely enumerate its models."""


@dataclass(frozen=True)
class DiscoveredRuntimeModel:
    """One provider identifier safe to present as a Studio choice."""

    provider_model_id: str


class ModelCatalogDiscoveryService:
    """Use a runtime connection only to discover provider-visible model IDs."""

    def __init__(self, runtime_connection_service: RuntimeConnectionService) -> None:
        self._runtime_connection_service = runtime_connection_service

    def discover(
        self, runtime_connection_id: str, context: TenantContext
    ) -> tuple[DiscoveredRuntimeModel, ...]:
        connection = self._runtime_connection_service.get(runtime_connection_id, context)
        provider = runtime_model_provider_key(connection.provider)
        _, config = self._runtime_connection_service.resolve_runtime_config(
            runtime_connection_id, connection.provider, context
        )
        if provider != "openai":
            raise ModelCatalogDiscoveryError(
                "This runtime provider does not support model-catalog discovery in OSS yet."
            )
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=str(config["api_key"]),
                base_url=_optional_string(config.get("base_url")),
                organization=_optional_string(config.get("organization")),
            )
            response = client.models.list()
            values = getattr(response, "data", response)
            identifiers = sorted(
                {
                    identifier
                    for item in values
                    if isinstance((identifier := getattr(item, "id", None)), str)
                    and identifier.strip()
                }
            )
        except Exception as exc:
            LOGGER.warning(
                "runtime_model_catalog_discovery_failed provider=%s error_type=%s",
                provider,
                type(exc).__name__,
            )
            raise ModelCatalogDiscoveryError(
                "The runtime provider model catalog could not be discovered. "
                "Confirm the runtime connection and its provider access."
            ) from exc
        return tuple(DiscoveredRuntimeModel(provider_model_id=value) for value in identifiers)


def _optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
