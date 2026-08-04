"""Benchmark model token speed (tokens/sec).

Measures input tokens, output tokens, latency, and throughput
for each configured model using the OpenAI-compatible API.

Defaults to OpenAI cloud. Override with env vars:
    OPENAI_BASE_URL=http://127.0.0.1:1234/v1   # LM Studio, Ollama, etc.
    OPENAI_API_KEY=lm-studio                     # ignored by most local servers

If OPENAI_BASE_URL is set and MODELS is empty, the script auto-discovers
models from the server and only benchmarks those that are currently loaded.
"""

import asyncio
import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv
load_dotenv()

from openai import AsyncOpenAI

# Models to benchmark (leave empty to auto-discover when using a custom base URL)
MODELS: list[str] = []

# Prompt sizes to test (in characters, ~chars/4 tokens)
PROMPT_SIZES_CHARS = [500, 2_000, 8_000]

# Target output tokens
OUTPUT_TOKENS = 100


@dataclass
class BenchmarkResult:
    model: str
    prompt_chars: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_s: float
    tokens_per_sec: float
    output_tokens_per_sec: float


async def discover_models(client: AsyncOpenAI) -> list[str]:
    """Fetch available models from the server."""
    try:
        resp = await client.models.list()
        ids = [m.id for m in resp.data]
        print(f"Discovered {len(ids)} model(s): {', '.join(ids)}\n")
        return ids
    except Exception as e:
        print(f"Warning: could not auto-discover models: {e}")
        return []


async def ping_model(client: AsyncOpenAI, model: str) -> bool:
    """Check if a model is loaded and responds to a simple request."""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
        )
        return resp.usage is not None
    except Exception:
        return False


async def filter_loaded_models(client: AsyncOpenAI, models: list[str]) -> list[str]:
    """Only keep models that are currently loaded and responding."""
    print("Checking which models are loaded and running...")
    loaded: list[str] = []
    for model in models:
        is_loaded = await ping_model(client, model)
        status = "loaded" if is_loaded else "unloaded / skipped"
        print(f"  {model}: {status}")
        if is_loaded:
            loaded.append(model)
    print()
    return loaded


async def benchmark_model(
    client: AsyncOpenAI, model: str, prompt_chars: int
) -> BenchmarkResult | None:
    # Build a prompt of roughly the desired size
    filler = "The quick brown fox jumps over the lazy dog. " * (prompt_chars // 60 + 1)
    prompt = filler[:prompt_chars]

    messages = [
        {"role": "user", "content": prompt},
    ]

    try:
        start = time.monotonic()
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=OUTPUT_TOKENS,
            temperature=0.1,
        )
        latency = time.monotonic() - start

        usage = response.usage
        if usage is None:
            print(f"  {model} / {prompt_chars} chars -> no usage info returned")
            return None

        total_tokens = usage.total_tokens
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens

        return BenchmarkResult(
            model=model,
            prompt_chars=prompt_chars,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_s=round(latency, 3),
            tokens_per_sec=round(total_tokens / latency, 2) if latency else 0,
            output_tokens_per_sec=round(output_tokens / latency, 2) if latency else 0,
        )
    except Exception as e:
        print(f"  {model} / {prompt_chars} chars -> ERROR: {e}")
        return None


async def run_benchmarks():
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("MODEL_REGISTRY_URL")

    # Ensure /v1 suffix for LM Studio compatibility
    if base_url and not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    if base_url:
        print(f"Using custom API endpoint: {base_url}")
        client = AsyncOpenAI(api_key=api_key or "lm-studio", base_url=base_url)
    else:
        if not api_key:
            print("ERROR: OPENAI_API_KEY not set and no OPENAI_BASE_URL provided.")
            return
        client = AsyncOpenAI(api_key=api_key)

    # Auto-discover models if using custom URL and MODELS is empty
    if base_url and not MODELS:
        discovered = await discover_models(client)
        if not discovered:
            print("No models found. Exiting.")
            return
        # Filter to only loaded/running models
        models = await filter_loaded_models(client, discovered)
        if not models:
            print("No loaded models found. Exiting.")
            return
    else:
        models = MODELS

    print(f"{'Model':<30} {'Prompt (chars)':>15} {'In tok':>8} {'Out tok':>8} "
          f"{'Total tok':>10} {'Latency(s)':>11} {'Tok/s':>8} {'Out tok/s':>10}")
    print("-" * 112)

    for model in models:
        for size in PROMPT_SIZES_CHARS:
            result = await benchmark_model(client, model, size)
            if result:
                print(
                    f"{result.model:<30} {result.prompt_chars:>15} "
                    f"{result.input_tokens:>8} {result.output_tokens:>8} "
                    f"{result.total_tokens:>10} {result.latency_s:>11.3f} "
                    f"{result.tokens_per_sec:>8.2f} {result.output_tokens_per_sec:>10.2f}"
                )


if __name__ == "__main__":
    print("Model Token Speed Benchmark")
    print(f"Output target: {OUTPUT_TOKENS} tokens\n")
    asyncio.run(run_benchmarks())
