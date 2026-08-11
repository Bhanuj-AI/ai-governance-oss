from __future__ import annotations

import re
from enum import Enum


class RuntimeModelProvider(str, Enum):
    """Canonical runtime endpoints available for managed model registration."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE_AI = "google_ai"
    GOOGLE_VERTEX_AI = "google_vertex_ai"
    AZURE_OPENAI = "azure_openai"
    AZURE_AI_FOUNDRY = "azure_ai_foundry"
    AWS_BEDROCK = "aws_bedrock"
    AWS_SAGEMAKER = "aws_sagemaker"
    MISTRAL = "mistral"
    COHERE = "cohere"
    XAI = "xai"
    DEEPSEEK = "deepseek"
    AI21 = "ai21"
    IBM_WATSONX = "ibm_watsonx"
    NVIDIA_NIM = "nvidia_nim"
    HUGGING_FACE_INFERENCE = "huggingface_inference"
    TOGETHER = "together"
    GROQ = "groq"
    FIREWORKS = "fireworks"
    PERPLEXITY = "perplexity"
    OLLAMA = "ollama"
    ALIBABA_QWEN = "alibaba_qwen"
    BAIDU_QIANFAN = "baidu_qianfan"
    TENCENT_HUNYUAN = "tencent_hunyuan"
    MOONSHOT = "moonshot"
    MINIMAX = "minimax"
    ZHIPU = "zhipu"
    CUSTOM = "custom"


_DISPLAY_NAMES = {
    RuntimeModelProvider.OPENAI: "OpenAI",
    RuntimeModelProvider.ANTHROPIC: "Anthropic",
    RuntimeModelProvider.GOOGLE_AI: "Google AI",
    RuntimeModelProvider.GOOGLE_VERTEX_AI: "Google Vertex AI",
    RuntimeModelProvider.AZURE_OPENAI: "Azure OpenAI",
    RuntimeModelProvider.AZURE_AI_FOUNDRY: "Azure AI Foundry",
    RuntimeModelProvider.AWS_BEDROCK: "Amazon Bedrock",
    RuntimeModelProvider.AWS_SAGEMAKER: "Amazon SageMaker",
    RuntimeModelProvider.MISTRAL: "Mistral AI",
    RuntimeModelProvider.COHERE: "Cohere",
    RuntimeModelProvider.XAI: "xAI",
    RuntimeModelProvider.DEEPSEEK: "DeepSeek",
    RuntimeModelProvider.AI21: "AI21 Labs",
    RuntimeModelProvider.IBM_WATSONX: "IBM watsonx",
    RuntimeModelProvider.NVIDIA_NIM: "NVIDIA NIM",
    RuntimeModelProvider.HUGGING_FACE_INFERENCE: "Hugging Face Inference",
    RuntimeModelProvider.TOGETHER: "Together AI",
    RuntimeModelProvider.GROQ: "Groq",
    RuntimeModelProvider.FIREWORKS: "Fireworks AI",
    RuntimeModelProvider.PERPLEXITY: "Perplexity",
    RuntimeModelProvider.OLLAMA: "Ollama",
    RuntimeModelProvider.ALIBABA_QWEN: "Alibaba Cloud Qwen",
    RuntimeModelProvider.BAIDU_QIANFAN: "Baidu Qianfan",
    RuntimeModelProvider.TENCENT_HUNYUAN: "Tencent Hunyuan",
    RuntimeModelProvider.MOONSHOT: "Moonshot AI",
    RuntimeModelProvider.MINIMAX: "MiniMax",
    RuntimeModelProvider.ZHIPU: "Zhipu AI",
    RuntimeModelProvider.CUSTOM: "Custom runtime",
}

_ALIASES = {
    "google": RuntimeModelProvider.GOOGLE_AI,
    "google_ai_studio": RuntimeModelProvider.GOOGLE_AI,
    "gemini": RuntimeModelProvider.GOOGLE_AI,
    "vertex_ai": RuntimeModelProvider.GOOGLE_VERTEX_AI,
    "google_vertex": RuntimeModelProvider.GOOGLE_VERTEX_AI,
    "azure": RuntimeModelProvider.AZURE_OPENAI,
    "bedrock": RuntimeModelProvider.AWS_BEDROCK,
    "amazon_bedrock": RuntimeModelProvider.AWS_BEDROCK,
    "sagemaker": RuntimeModelProvider.AWS_SAGEMAKER,
    "amazon_sagemaker": RuntimeModelProvider.AWS_SAGEMAKER,
    "mistral_ai": RuntimeModelProvider.MISTRAL,
    "ibm_watsonx_ai": RuntimeModelProvider.IBM_WATSONX,
    "huggingface": RuntimeModelProvider.HUGGING_FACE_INFERENCE,
    "hugging_face": RuntimeModelProvider.HUGGING_FACE_INFERENCE,
    "together_ai": RuntimeModelProvider.TOGETHER,
    "fireworks_ai": RuntimeModelProvider.FIREWORKS,
    "alibaba_cloud_qwen": RuntimeModelProvider.ALIBABA_QWEN,
    "baidu": RuntimeModelProvider.BAIDU_QIANFAN,
    "tencent": RuntimeModelProvider.TENCENT_HUNYUAN,
    "moonshot_ai": RuntimeModelProvider.MOONSHOT,
    "zhipu_ai": RuntimeModelProvider.ZHIPU,
    "other": RuntimeModelProvider.CUSTOM,
}


def runtime_model_provider_key(value: str) -> str | None:
    """Resolve a managed-registration provider value to its canonical key."""

    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if normalized.startswith(f"{RuntimeModelProvider.CUSTOM.value}_"):
        return RuntimeModelProvider.CUSTOM.value
    if normalized in RuntimeModelProvider._value2member_map_:
        return normalized
    provider = _ALIASES.get(normalized)
    return provider.value if provider is not None else None


def runtime_model_provider_display_name(value: str) -> str:
    """Return the operator-facing label for a canonical provider key."""

    return _DISPLAY_NAMES[RuntimeModelProvider(value)]


def known_runtime_model_provider_keys() -> tuple[str, ...]:
    """Return the stable built-in vocabulary in UI display order."""

    return tuple(provider.value for provider in RuntimeModelProvider)
