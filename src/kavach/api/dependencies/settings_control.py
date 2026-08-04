from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Depends, Request

from kavach.repositories.factories.sqlite_database import create_sqlite_database
from kavach.settings_control import (
    ConfigurationService,
    InMemorySettingsRepository,
    PostgresSettingsRepository,
    SQLiteSettingsRepository,
)
from kavach.api.dependencies.events import get_event_publisher
from kavach.events import EventPublisher


@lru_cache(maxsize=1)
def get_settings_repository():
    backend = os.getenv("KAVACH_SETTINGS_REPOSITORY", "inmemory").strip().lower()
    if backend == "inmemory":
        return InMemorySettingsRepository()
    if backend == "sqlite":
        path = os.getenv("KAVACH_SETTINGS_SQLITE_PATH")
        if not path:
            raise ValueError(
                "KAVACH_SETTINGS_SQLITE_PATH is required for sqlite settings"
            )
        return SQLiteSettingsRepository(create_sqlite_database(path))
    if backend == "postgres":
        dsn = os.getenv("KAVACH_SETTINGS_POSTGRES_DSN")
        if not dsn:
            raise ValueError(
                "KAVACH_SETTINGS_POSTGRES_DSN is required for postgres settings"
            )
        return PostgresSettingsRepository(dsn)
    raise ValueError(f"Unsupported settings repository backend: {backend}")


def get_configuration_service(
    request: Request = None,
    event_publisher: EventPublisher = Depends(get_event_publisher),
) -> ConfigurationService:
    """Build configuration updates with the application-scoped event publisher."""
    return ConfigurationService(
        get_settings_repository(),
        event_publisher=event_publisher,
        authorization_enforcers=tuple(
            getattr(request.app.state, "plugin_authorization_enforcers", ())
            if request is not None
            else ()
        ),
    )


@lru_cache(maxsize=1)
def get_provider_installation_repository():
    """Expose typed provider installations through the durable settings store."""
    from kavach.repositories.settings_provider_installation_repository import (
        SettingsProviderInstallationRepository,
    )

    return SettingsProviderInstallationRepository(get_settings_repository())
