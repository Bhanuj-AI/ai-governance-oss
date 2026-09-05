"""Dependency provider for the runtime finding repository.

Exposed separately from the service so that seeding and admin
operations can write directly to the repository without going
through the service layer.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def get_runtime_finding_repository():
    """Return the runtime finding repository instance.

    Repository construction is delegated here so that seeding code
    can persist findings directly without importing from the service layer.
    """
    from ai_governance.repositories.factories import (
        RuntimeFindingRepositoryFactory,
    )
    from ai_governance.settings import load_settings

    settings = load_settings()
    return RuntimeFindingRepositoryFactory(settings).create()
