"""Release-smoke the governed replay walkthrough against a running AI Governance Control Plane API.

Run this after the target stack is started. It invokes the installed ``ai-governance``
command twice, so the validation exercises the same public API path that a
user, demo, or CI job uses. The selected persistence backend is deliberately
opaque to this script.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


REQUIRED_RESOURCES = {
    "prompt_id",
    "model_id",
    "dataset_id",
    "source_execution_id",
    "baseline_evaluation_id",
    "decision_id",
    "replay_id",
}
REQUIRED_URLS = {
    "prompt",
    "model",
    "dataset",
    "source_execution",
    "decision",
    "replay",
    "lineage",
}


def main() -> None:
    api_url = os.getenv("AI_GOVERNANCE_SMOKE_API_URL")
    if not api_url:
        raise SystemExit("Set AI_GOVERNANCE_SMOKE_API_URL to the running AI Governance Control Plane API.")

    with TemporaryDirectory(prefix="ai-governance-governed-replay-smoke-") as tmpdir:
        first = _run(Path(tmpdir) / "first.json", api_url)
        second = _run(Path(tmpdir) / "second.json", api_url)

    _assert_manifest(first)
    _assert_manifest(second)
    if first["resources"] != second["resources"]:
        raise AssertionError("Repeated walkthrough created or selected different resources.")

    print("[governed replay walkthrough]")
    print(f"api_version={first['api_version']}")
    print(f"tenant={first['tenant_id']}")
    print(f"replay_id={first['resources']['replay_id']}")
    print("idempotency=verified")


def _run(manifest_path: Path, api_url: str) -> dict[str, Any]:
    command = [
        "ai-governance",
        "walkthrough",
        "governed-replay",
        "--api-url",
        api_url,
        "--studio-url",
        os.getenv("AI_GOVERNANCE_SMOKE_STUDIO_URL", "http://localhost:3000"),
        "--organization-id",
        os.getenv("AI_GOVERNANCE_SMOKE_ORGANIZATION_ID", "org_default"),
        "--project-id",
        os.getenv("AI_GOVERNANCE_SMOKE_PROJECT_ID", "project_default"),
        "--non-interactive",
        "--output-json",
        "--manifest",
        str(manifest_path),
    ]
    token = os.getenv("AI_GOVERNANCE_SMOKE_TOKEN")
    if token:
        command.extend(("--token", token))
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(
            f"Walkthrough smoke command failed ({result.returncode}): {result.stderr}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Walkthrough did not emit JSON: {result.stdout}") from exc


def _assert_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("api_version") != "v1":
        raise AssertionError(f"Unexpected walkthrough API version: {manifest.get('api_version')}")
    if manifest.get("outcome") != "COMPLETED":
        raise AssertionError(f"Walkthrough did not complete: {manifest.get('failure')}")
    resources = manifest.get("resources", {})
    missing_resources = REQUIRED_RESOURCES - resources.keys()
    if missing_resources:
        raise AssertionError(f"Manifest omitted resources: {sorted(missing_resources)}")
    urls = manifest.get("urls", {})
    missing_urls = REQUIRED_URLS - urls.keys()
    if missing_urls:
        raise AssertionError(f"Manifest omitted deep links: {sorted(missing_urls)}")


if __name__ == "__main__":
    main()
