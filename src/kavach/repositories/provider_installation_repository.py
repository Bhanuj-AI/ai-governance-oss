"""Persistence-neutral provider-installation repository contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from kavach.domain.provider_installation import ProviderInstallation


class ProviderInstallationRepository(ABC):
    @abstractmethod
    def save(self, installation: ProviderInstallation) -> ProviderInstallation:
        """Create or replace an installation within its tenant scope."""

    @abstractmethod
    def find_by_id(
        self, installation_id: str, organization_id: str, project_id: str | None
    ) -> ProviderInstallation | None:
        """Return one installation only when it belongs to the supplied scope."""

    @abstractmethod
    def list_for_scope(
        self, organization_id: str, project_id: str | None
    ) -> list[ProviderInstallation]:
        """Return installations in deterministic display-name order."""
