"""Structural lifecycle contracts implemented by external runtime plugins."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from bhanuj_governance_plugin_api.contracts import ReplayExecutionAdapterContribution
from bhanuj_governance_plugin_api.metadata import PluginMetadata


class ReplayAdapterContributionRegistry(Protocol):
    """The bounded host registration surface needed by runtime plugins."""

    def replay_execution_adapters(
        self, items: Iterable[ReplayExecutionAdapterContribution]
    ) -> None: ...


class PluginContext(Protocol):
    """Plugin-bound context exposed by a host during lifecycle callbacks."""

    @property
    def contributions(self) -> ReplayAdapterContributionRegistry: ...


class AIGovernancePlugin(Protocol):
    """Stable lifecycle protocol for an independently installed plugin."""

    @property
    def metadata(self) -> PluginMetadata: ...

    def validate(self, context: PluginContext) -> None: ...

    def register(self, context: PluginContext) -> None: ...

    def start(self, context: PluginContext) -> None: ...

    def stop(self, context: PluginContext) -> None: ...
