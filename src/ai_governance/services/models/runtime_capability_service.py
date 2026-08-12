"""Provider-neutral capability profiles used by managed model registration."""

from __future__ import annotations

from ai_governance.domain.models import (
    ModelRuntimeCapabilitySnapshot,
    RuntimeCapabilityVerification,
    RuntimeParameterCapability,
    runtime_model_provider_key,
)


def resolve_runtime_capabilities(
    provider: str, model_name: str
) -> ModelRuntimeCapabilitySnapshot:
    """Return the deterministic contract used for a newly registered model.

    This resolver deliberately does not call a provider at execution time.
    A future adapter may enrich registration with a live verification, but the
    resulting profile remains the immutable contract for this model version.
    """

    provider_key = runtime_model_provider_key(provider)
    model_key = model_name.strip().lower()
    if provider_key == "openai":
        is_reasoning = model_key.startswith(("gpt-5", "o1", "o3", "o4"))
        return ModelRuntimeCapabilitySnapshot(
            profile_id=(
                "openai-chat-completions-reasoning"
                if is_reasoning
                else "openai-chat-completions-standard"
            ),
            profile_version="1",
            invocation_contract="openai-chat-completions",
            verification=RuntimeCapabilityVerification.DECLARED,
            parameters=(
                RuntimeParameterCapability(
                    name="max_output_tokens",
                    supported=True,
                    value_type="integer",
                    minimum=1,
                ),
                RuntimeParameterCapability(
                    name="temperature",
                    supported=not is_reasoning,
                    value_type="number",
                    minimum=0,
                    maximum=2,
                    default=1,
                ),
                RuntimeParameterCapability(
                    name="top_p",
                    supported=not is_reasoning,
                    value_type="number",
                    minimum=0,
                    maximum=1,
                    default=1,
                ),
            ),
        )
    if provider_key == "custom":
        return ModelRuntimeCapabilitySnapshot(
            profile_id="openai-compatible-declared",
            profile_version="1",
            invocation_contract="openai-compatible-chat-completions",
            verification=RuntimeCapabilityVerification.DECLARED,
            parameters=(
                RuntimeParameterCapability("max_output_tokens", True, "integer", minimum=1),
                RuntimeParameterCapability("temperature", True, "number", minimum=0, maximum=2),
                RuntimeParameterCapability("top_p", True, "number", minimum=0, maximum=1),
            ),
        )
    return ModelRuntimeCapabilitySnapshot(
        profile_id=f"{provider_key}-unverified",
        profile_version="1",
        invocation_contract="provider-specific",
        verification=RuntimeCapabilityVerification.UNVERIFIED,
        parameters=(),
    )
