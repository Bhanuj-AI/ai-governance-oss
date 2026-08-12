from ai_governance.services.models import resolve_runtime_capabilities


def test_openai_reasoning_profile_rejects_sampling_controls() -> None:
    capabilities = resolve_runtime_capabilities("openai", "gpt-5.5")

    assert capabilities.invocation_contract == "openai-chat-completions"
    assert capabilities.supports("max_output_tokens") is True
    assert capabilities.supports("temperature") is False
    assert capabilities.supports("top_p") is False


def test_openai_standard_profile_supports_sampling_controls() -> None:
    capabilities = resolve_runtime_capabilities("openai", "gpt-4.1")

    assert capabilities.supports("max_output_tokens") is True
    assert capabilities.supports("temperature") is True
    assert capabilities.supports("top_p") is True
