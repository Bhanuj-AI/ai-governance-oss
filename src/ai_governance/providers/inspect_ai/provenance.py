from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ai_governance.providers.inspect_ai.config import InspectRunnerConfig
from ai_governance.providers.provider_descriptor import scrub_sensitive_metadata


def configuration_provenance(
    config: InspectRunnerConfig,
    *,
    inspect_version: str,
    adapter_version: str = "1.0.3",
    dataset_version: str | None,
) -> dict[str, Any]:
    """Return immutable, secret-free execution evidence and its fingerprint."""
    solver_config = scrub_sensitive_metadata(config.solver_config)
    model_args = scrub_sensitive_metadata(config.model_args)
    environment = scrub_sensitive_metadata(config.metadata)
    provenance = {
        "runner_type": "inspect_ai",
        "inspect_version": inspect_version,
        "adapter_version": adapter_version,
        "model_identifier": config.model,
        "tasks": list(config.tasks),
        "task_version": config.task_version or dataset_version or "unknown",
        "solver_identifier": config.solver,
        "resolved_solver_config": solver_config,
        "solver_config_digest": _digest(solver_config),
        "resolved_model_args": model_args,
        "model_args_digest": _digest(model_args),
        "scorer_identifier": config.scorer,
        "scorer_version": config.scorer_version,
        "execution_limits": {
            "task_limit": config.task_limit,
            "token_limit": config.token_limit,
            "timeout_seconds": config.timeout_seconds,
            "max_connections": config.max_connections,
        },
        "requires_tools": config.requires_tools,
        "declared_call_attribution": _declared_call_attribution(config),
        "environment_config_digest": _digest(environment),
    }
    return {**provenance, "configuration_fingerprint": _digest(provenance)}


def _digest(value: Mapping[str, Any]) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(serialized.encode()).hexdigest()}"


def _declared_call_attribution(config: InspectRunnerConfig) -> list[dict[str, object]]:
    solver = config.solver.rsplit(":", 1)[-1]
    if solver in {"planner_executor_generate", "incident_planner_executor_generate"}:
        return [
            {
                "call_role": "planning",
                "original_task_included": True,
                "prior_conversation_retained": False,
            },
            {
                "call_role": "execution",
                "original_task_included": True,
                "prior_conversation_retained": True,
            },
        ]
    if solver == "generate":
        return [
            {
                "call_role": "direct_generation",
                "original_task_included": True,
                "prior_conversation_retained": False,
            }
        ]
    return []
