"""Persistence-neutral repository contract for tenant runtime connections."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.domain.runtime_connection import RuntimeConnection


class RuntimeConnectionRepository(ABC):
    @abstractmethod
    def save(self, connection: RuntimeConnection) -> RuntimeConnection:
        """Create or replace a runtime connection within its tenant scope."""

    @abstractmethod
    def find_by_id(
        self, runtime_connection_id: str, organization_id: str, project_id: str | None
    ) -> RuntimeConnection | None:
        """Return one connection only when it belongs to the supplied scope."""

    @abstractmethod
    def list_for_scope(
        self, organization_id: str, project_id: str | None
    ) -> list[RuntimeConnection]:
        """Return connections in deterministic display-name order."""

