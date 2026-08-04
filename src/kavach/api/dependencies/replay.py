"""Replay Management dependency wiring."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Depends, Request

from kavach.api.dependencies.repositories import (
    get_job_repository,
    get_replay_repository,
    get_replay_result_repository,
)
from kavach.api.dependencies.events import get_event_publisher
from kavach.api.dependencies.jobs import get_job_api_service
from kavach.events import EventPublisher
from kavach.api.dependencies.settings_control import get_configuration_service
from kavach.api.dependencies.provider_installations import get_provider_installation_service
from kavach.services.replay_execution_discovery import InMemoryReplayExecutionCatalog


@lru_cache(maxsize=1)
def get_replay_execution_catalog() -> InMemoryReplayExecutionCatalog:
    """Return the local source catalog; production deployments override this.

    The contract supports a projected, tenant-scoped search index. The bundled
    implementation exists for development/demo data and tests only.
    """
    from kavach.repositories.factories.replay_execution_catalog_factory import (
        ReplayExecutionCatalogFactory,
    )
    from kavach.settings import load_settings

    return ReplayExecutionCatalogFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_replay_source_resolver() -> Any:
    """Return the authoritative replay source store for this deployment.

    The selected store is shared by API and worker processes. Catalog entries
    remain compact search projections and are not used to reconstruct sources.
    """
    from kavach.repositories.factories.replay_execution_store_factory import (
        ReplayExecutionStoreFactory,
    )
    from kavach.settings import load_settings

    return ReplayExecutionStoreFactory(load_settings()).create()


def get_replay_application_service(
    request: Request,
    replay_repository: Any = Depends(get_replay_repository),
    job_service: Any = Depends(get_job_api_service),
    configuration_service: Any = Depends(get_configuration_service),
    result_repository: Any = Depends(get_replay_result_repository),
    source_resolver: Any = Depends(get_replay_source_resolver),
    provider_installation_service: Any = Depends(get_provider_installation_service),
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> Any:
    """Build the Replay service with its exact source-resolution boundary."""

    from kavach.services.replay_application_service import ReplayApplicationService

    return ReplayApplicationService(
        replay_repository=replay_repository,
        source_resolver=source_resolver,
        job_service=job_service,
        configuration_service=configuration_service,
        result_repository=result_repository,
        provider_installation_service=provider_installation_service,
        event_publisher=event_publisher,
        authorization_enforcers=tuple(
            getattr(request.app.state, "plugin_authorization_enforcers", ())
        ),
    )


def get_replay_audit_service(
    replay_service: Any = Depends(get_replay_application_service),
    job_repository: Any = Depends(get_job_repository),
) -> Any:
    """Build the read-only timeline for one authorized replay."""

    from kavach.services.replay_audit_service import ReplayAuditService

    return ReplayAuditService(
        replay_reader=replay_service,
        job_repository=job_repository,
    )
