"""Provider-neutral contract for governed text-generation adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ai_governance.providers.provider_descriptor import ProviderDescriptor


@dataclass(frozen=True)
class LLMCompletion:
    """A normalized text-generation result without provider-specific payloads."""

    text: str
    model: str
    usage: Mapping[str, int] = field(default_factory=dict)
    provider_metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMModelDescriptor:
    """A provider-owned model option that can be safely presented to a user."""

    model_id: str
    display_name: str
    reasoning_efforts: tuple[str, ...] = ()
    default_reasoning_effort: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "display_name": self.display_name,
            "reasoning_efforts": list(self.reasoning_efforts),
            "default_reasoning_effort": self.default_reasoning_effort,
            "metadata": dict(self.metadata),
        }


class LLMProvider(Protocol):
    """Governed adapter for a single text-generation provider."""

    @property
    def descriptor(self) -> ProviderDescriptor:
        """Return secret-free provider identity and capability metadata."""
        ...

    def models(self) -> tuple[LLMModelDescriptor, ...]:
        """List the governed models and controls supported by this adapter."""
        ...

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        reasoning_effort: str | None = None,
    ) -> LLMCompletion:
        """Generate one completion from provider-neutral prompt inputs."""
        ...


__all__ = ["LLMCompletion", "LLMModelDescriptor", "LLMProvider"]
