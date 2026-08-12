from __future__ import annotations

import sys
from types import SimpleNamespace

from ai_governance.services.model_catalog_discovery_service import (
    ModelCatalogDiscoveryService,
)
from ai_governance.tenancy.domain import TenantContext


class _RuntimeConnections:
    def get(self, connection_id: str, context: TenantContext) -> SimpleNamespace:
        assert connection_id == "connection-1"
        return SimpleNamespace(provider="openai")

    def resolve_runtime_config(
        self, connection_id: str, provider: str, context: TenantContext
    ) -> tuple[object, dict[str, str]]:
        assert (connection_id, provider) == ("connection-1", "openai")
        return object(), {"api_key": "secret"}


def test_discovers_openai_model_ids_from_the_selected_runtime_connection(
    monkeypatch,
) -> None:
    class _OpenAI:
        def __init__(self, **_kwargs: object) -> None:
            self.models = SimpleNamespace(
                list=lambda: SimpleNamespace(
                    data=[SimpleNamespace(id="gpt-4.1-mini"), SimpleNamespace(id="gpt-5")]
                )
            )

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI))

    models = ModelCatalogDiscoveryService(_RuntimeConnections()).discover(
        "connection-1", TenantContext("org", "project", "actor", "request")
    )

    assert [model.provider_model_id for model in models] == ["gpt-4.1-mini", "gpt-5"]
