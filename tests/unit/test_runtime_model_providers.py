from ai_governance.domain.models import (
    RuntimeModelProvider,
    known_runtime_model_provider_keys,
    runtime_model_provider_display_name,
    runtime_model_provider_key,
)


def test_runtime_model_provider_vocabulary_contains_global_runtime_endpoints() -> None:
    providers = known_runtime_model_provider_keys()

    assert RuntimeModelProvider.OPENAI.value in providers
    assert RuntimeModelProvider.AWS_BEDROCK.value in providers
    assert RuntimeModelProvider.GOOGLE_VERTEX_AI.value in providers
    assert RuntimeModelProvider.ALIBABA_QWEN.value in providers
    assert RuntimeModelProvider.CUSTOM.value in providers


def test_runtime_model_provider_normalizes_known_aliases_and_custom_endpoints() -> None:
    assert runtime_model_provider_key("OpenAI") == "openai"
    assert runtime_model_provider_key("Amazon Bedrock") == "aws_bedrock"
    assert runtime_model_provider_key("custom:enterprise-gateway") == "custom"
    assert runtime_model_provider_key("private-runtime") is None


def test_runtime_model_provider_returns_operator_display_name() -> None:
    assert runtime_model_provider_display_name("azure_openai") == "Azure OpenAI"
