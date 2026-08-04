"""Public lifecycle contract implemented by Kavach plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from kavach.plugins.metadata import PluginMetadata

if TYPE_CHECKING:
    from kavach.plugins.registry import PluginContext


class KavachPlugin(Protocol):
    """Stable lifecycle protocol implemented by every Kavach extension.

    Kavach calls the methods in this order: :attr:`metadata`, ``validate()``,
    ``register()``, ``start()``, and finally ``stop()`` during application
    shutdown. Registration must only use the supplied :class:`PluginContext`;
    plugins must not reach into Kavach services, repositories, or application
    globals. A lifecycle exception fails startup, apart from shutdown errors,
    which are logged while the remaining plugins are stopped.
    """
    @property
    def metadata(self) -> PluginMetadata:
        """Return immutable identity, version compatibility, and capabilities."""
        ...

    def register(self, context: PluginContext) -> None:
        """Contribute providers, hooks, subscriptions, and routes through context.

        This runs once after compatibility and plugin validation, before the
        FastAPI application starts. It must not start background work; reserve
        that for :meth:`start` so a failed route or provider claim cannot leave
        a partially running extension behind.
        """
        ...

    def validate(self, context: PluginContext) -> None:
        """Validate plugin-local configuration and required dependencies.

        Raise an exception to prevent registration and fail application startup
        with a diagnostic plugin identity. Validation must be side-effect free.
        """
        ...

    def start(self, context: PluginContext) -> None:
        """Start runtime work only after all plugin contributions are installed."""
        ...

    def stop(self, context: PluginContext) -> None:
        """Release plugin-owned runtime resources during reverse-order shutdown."""
        ...
