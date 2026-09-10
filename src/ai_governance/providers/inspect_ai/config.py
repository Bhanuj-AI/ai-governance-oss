from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ai_governance.providers.inspect_ai.errors import InspectRunnerError
from ai_governance.providers.provider_descriptor import scrub_sensitive_metadata


@dataclass(frozen=True)
class InspectRunnerConfig:
    """Secret-free, bounded configuration for a single Inspect invocation."""

    model: str
    tasks: tuple[str, ...]
    solver: str
    solver_config: Mapping[str, Any] = field(default_factory=dict)
    model_args: Mapping[str, Any] = field(default_factory=dict)
    scorer: str | None = None
    scorer_version: str | None = None
    task_version: str | None = None
    task_limit: int | None = None
    token_limit: int | None = None
    timeout_seconds: int | None = None
    max_connections: int | None = None
    requires_tools: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        model = self.model.strip()
        solver = self.solver.strip()
        tasks = tuple(task.strip() for task in self.tasks if task.strip())
        if not isinstance(self.requires_tools, bool):
            raise InspectRunnerError("Inspect requires_tools must be a boolean.")
        if not model:
            raise InspectRunnerError(
                "Inspect requires a configured model.", category="model_failure"
            )
        if not solver:
            raise InspectRunnerError(
                "Inspect requires a solver or scaffold identifier.",
                category="scaffold_failure",
            )
        if not tasks:
            raise InspectRunnerError(
                "Inspect requires at least one bounded task.",
                category="task_definition_failure",
            )
        if any(
            "/" in task
            or "\\" in task
            or task.startswith("file:")
            or ":" not in task
            for task in tasks
        ):
            raise InspectRunnerError(
                "Inspect tasks must be packaged 'module:callable' identifiers, not host-local paths.",
                category="task_definition_failure",
            )
        if self.task_limit is not None and self.task_limit <= 0:
            raise InspectRunnerError("Inspect task_limit must be greater than zero.")
        if self.token_limit is not None and self.token_limit <= 0:
            raise InspectRunnerError("Inspect token_limit must be greater than zero.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise InspectRunnerError("Inspect timeout_seconds must be greater than zero.")
        if self.max_connections is not None and self.max_connections <= 0:
            raise InspectRunnerError("Inspect max_connections must be greater than zero.")
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "solver", solver)
        object.__setattr__(self, "tasks", tasks)
        object.__setattr__(self, "solver_config", scrub_sensitive_metadata(self.solver_config))
        object.__setattr__(self, "model_args", scrub_sensitive_metadata(self.model_args))
        object.__setattr__(self, "metadata", scrub_sensitive_metadata(self.metadata))

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
        *,
        default_task: str,
        require_solver: bool = True,
    ) -> InspectRunnerConfig:
        raw_tasks = values.get("tasks", (default_task,))
        if isinstance(raw_tasks, str):
            raw_tasks = (raw_tasks,)
        if not isinstance(raw_tasks, Sequence):
            raise InspectRunnerError(
                "Inspect tasks must be a list of task identifiers.",
                category="task_definition_failure",
            )
        solver = str(values.get("solver") or values.get("scaffold") or "")
        # An installation describes the fixed runner connection.  A candidate
        # supplies the scaffold, so validate those separately rather than make
        # an installation identifier an accidental experimental variable.
        if not solver and not require_solver:
            solver = "__candidate_supplied__"
        return cls(
            model=str(values.get("model") or ""),
            tasks=tuple(str(task) for task in raw_tasks),
            solver=solver,
            solver_config=dict(values.get("solver_config") or values.get("scaffold_config") or {}),
            model_args=dict(values.get("model_args") or {}),
            scorer=_optional_string(values.get("scorer")),
            scorer_version=_optional_string(values.get("scorer_version")),
            task_version=_optional_string(values.get("task_version")),
            task_limit=_optional_int(values.get("task_limit")),
            token_limit=_optional_int(values.get("token_limit")),
            timeout_seconds=_optional_int(values.get("timeout_seconds")),
            max_connections=_optional_int(values.get("max_connections")),
            requires_tools=_optional_bool(values.get("requires_tools", False)),
            metadata=dict(values.get("metadata") or {}),
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise InspectRunnerError("Inspect execution limits must be integers.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InspectRunnerError("Inspect execution limits must be integers.") from exc


def _optional_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    raise InspectRunnerError("Inspect requires_tools must be a boolean.")
