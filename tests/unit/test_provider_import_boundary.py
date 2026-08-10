from __future__ import annotations

from pathlib import Path


def test_provider_sdk_imports_are_isolated_to_trulens_adapter_folder() -> None:
    src_root = Path(__file__).parents[2] / "src" / "ai-governance"
    violations: list[str] = []

    for path in src_root.rglob("*.py"):
        relative = path.relative_to(src_root)
        source = path.read_text(encoding="utf-8")
        has_provider_sdk_import = any(
            pattern in source
            for pattern in (
                "from trulens",
                "import trulens",
                "from openai",
                "import openai",
                "from trulens.providers.openai import OpenAI",
            )
        )

        if has_provider_sdk_import and not str(relative).startswith(
            "providers/trulens/"
        ):
            violations.append(str(relative))

    assert violations == []
