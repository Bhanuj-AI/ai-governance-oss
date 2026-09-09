from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import uuid4

from ai_governance.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
    EvaluationSampleResult,
)
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.providers.evaluation_provider import (
    BatchEvaluationResult,
    EvaluationProvider,
    EvaluationWorkloadEstimate,
)
from ai_governance.providers.inspect_ai.config import InspectRunnerConfig
from ai_governance.providers.inspect_ai.errors import InspectRunnerError
from ai_governance.providers.inspect_ai.provenance import configuration_provenance
from ai_governance.providers.provider_capabilities import (
    EvaluationGranularity,
    ProviderCapabilities,
)
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.providers.schema_loader import load_provider_configuration_schema

_METRICS = (
    "pass",
    "score",
    "tool_action_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "wall_clock_duration_seconds",
    "estimated_model_cost",
)


class InspectEvaluationRunner(EvaluationProvider):
    """Optional Inspect AI adapter behind the existing evaluation-provider SPI.

    The runner deliberately accepts and returns only control-plane types. The
    narrow ``executor`` seam makes unit tests independent of the Inspect SDK
    and keeps provider SDK objects out of the domain and service layers.
    """

    def __init__(
        self,
        executor: Callable[[InspectRunnerConfig], object] | None = None,
    ) -> None:
        self._executor = executor

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="inspect_ai",
            display_name="Inspect AI",
            version=self._inspect_version(),
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=_METRICS,
                supported_evaluation_modes=("sync", "async"),
                supports_batch=True,
                supports_async=True,
                supports_artifacts=True,
                supports_explanations=True,
                supports_row_level_results=True,
                evaluation_granularity=EvaluationGranularity.BATCH,
            ),
            configuration_schema=load_provider_configuration_schema("inspect_ai"),
            metadata={"runtime_dependency": "inspect-ai"},
        )

    def validate_configuration(self, provider_config: Mapping[str, Any]) -> None:
        config = InspectRunnerConfig.from_mapping(
            provider_config,
            default_task="configured-task",
            require_solver=False,
        )
        _validate_supported_tool_transport(config)
        if self._executor is None:
            self._require_installation()

    def validate_run_configuration(
        self,
        provider_config: Mapping[str, Any],
    ) -> None:
        """Reject known unsupported tool/model combinations before dispatch."""
        config = InspectRunnerConfig.from_mapping(
            provider_config,
            default_task="configured-task",
        )
        _validate_supported_tool_transport(config)

    def execution_timeout_seconds(
        self,
        provider_config: Mapping[str, Any],
    ) -> int | None:
        """Expose Inspect's configured per-invocation bound to the worker."""
        return InspectRunnerConfig.from_mapping(
            provider_config,
            default_task="configured-task",
        ).timeout_seconds

    def estimate_workload(
        self,
        provider_config: Mapping[str, Any],
    ) -> EvaluationWorkloadEstimate:
        """Return the bounded sample volume for one Inspect invocation.

        Inspect evaluates its configured task set in one runner invocation.
        ``task_limit`` is a per-task bound, so a known sample count is the
        number of tasks multiplied by that limit. The number of model calls is
        intentionally not claimed: a scaffold can use a variable number.
        """
        config = InspectRunnerConfig.from_mapping(
            provider_config,
            default_task="configured-task",
        )
        sample_count = (
            len(config.tasks) * config.task_limit
            if config.task_limit is not None
            else None
        )
        return EvaluationWorkloadEstimate(
            runner_invocation_count=1,
            expected_sample_result_count=sample_count,
        )

    def capture_runner_provenance(
        self,
        provider_config: Mapping[str, Any],
        dataset_version: str,
    ) -> dict[str, Any]:
        """Freeze secret-free runner evidence before a candidate run starts."""
        config = InspectRunnerConfig.from_mapping(
            provider_config, default_task="configured-task"
        )
        return configuration_provenance(
            config,
            inspect_version=self._inspect_version(),
            dataset_version=dataset_version,
        )

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        config = InspectRunnerConfig.from_mapping(
            request.provider_config,
            default_task=request.execution.workflow_name,
        )
        provenance = configuration_provenance(
            config,
            inspect_version=self._inspect_version(),
            dataset_version=_dataset_version(request),
        )
        try:
            raw = self._execute(config)
            return self._normalize(request, raw, provenance)
        except InspectRunnerError:
            raise
        except Exception as exc:
            raise InspectRunnerError(
                f"Inspect evaluation runner failed: {type(exc).__name__}.",
                category="infrastructure_failure",
            ) from exc

    def evaluate_batch(self, request: EvaluationRequest) -> BatchEvaluationResult:
        """Execute one Inspect task set and return its provider-neutral samples."""
        config = InspectRunnerConfig.from_mapping(
            request.provider_config,
            default_task=request.execution.workflow_name,
        )
        provenance = configuration_provenance(
            config,
            inspect_version=self._inspect_version(),
            dataset_version=_dataset_version(request),
        )
        try:
            raw = self._execute(config)
            samples = tuple(
                _sample_result(record, index=index, provenance=provenance)
                for index, record in enumerate(_records(raw), start=1)
            )
            return BatchEvaluationResult(
                sample_results=samples,
                artifacts=tuple(_batch_artifacts(raw)),
                metadata={
                    "provider": "inspect_ai",
                    "runner_provenance": provenance,
                    "completion_status": "completed",
                },
            )
        except InspectRunnerError:
            raise
        except Exception as exc:
            raise InspectRunnerError(
                f"Inspect batch evaluation failed: {type(exc).__name__}.",
                category="infrastructure_failure",
            ) from exc

    def _execute(self, config: InspectRunnerConfig) -> object:
        if self._executor is not None:
            return self._executor(config)
        self._require_installation()
        try:
            from inspect_ai import (
                eval as inspect_eval,  # type: ignore[import-not-found]
            )
        except ImportError as exc:  # defensive for package layouts
            raise InspectRunnerError(
                "Inspect AI is unavailable. Install the ai-governance[inspect] extra."
            ) from exc
        kwargs: dict[str, Any] = {
            "tasks": [_resolve_task(task) for task in config.tasks],
            "model": config.model,
            "solver": _resolve_solver(config),
        }
        if config.task_limit is not None:
            kwargs["limit"] = config.task_limit
        if config.max_connections is not None:
            kwargs["max_connections"] = config.max_connections
        if config.timeout_seconds is not None:
            kwargs["timeout"] = config.timeout_seconds
        return inspect_eval(**kwargs)

    def _normalize(
        self,
        request: EvaluationRequest,
        raw: object,
        provenance: Mapping[str, Any],
    ) -> EvaluationResult:
        records = _records(raw)
        values: dict[str, list[float]] = {"pass": []}
        statuses: list[str] = []
        raw_refs: list[str] = []
        aliases_by_metric = {
            "score": ("score",),
            "tool_action_count": ("tool_action_count", "tool_calls", "actions"),
            "input_tokens": ("input_tokens", "tokens_input"),
            "output_tokens": ("output_tokens", "tokens_output"),
            "total_tokens": ("total_tokens", "tokens"),
            "wall_clock_duration_seconds": (
                "wall_clock_duration_seconds",
                "duration_seconds",
                "duration",
            ),
            "estimated_model_cost": ("estimated_model_cost", "model_cost", "cost"),
        }
        for record in records:
            status = str(_value(record, "status") or "unknown").lower()
            error = _value(record, "error") or _value(record, "error_message")
            if error or status in {"error", "failed", "cancelled", "timeout"}:
                raise InspectRunnerError(
                    f"Inspect evaluation reported {status}: {str(error or 'no details')[:300]}",
                    category=_failure_category(error, status),
                )
            statuses.append(status)
            score = _record_score(record)
            values["pass"].append(
                1.0 if _boolean(_value(record, "passed"), score) else 0.0
            )
            if score is not None:
                values.setdefault("score", []).append(score)
            for metric_name, aliases in aliases_by_metric.items():
                value = next(
                    (
                        numeric
                        for alias in aliases
                        if (numeric := _number(_value(record, alias))) is not None
                    ),
                    None,
                )
                if value is None:
                    value = _inspect_sample_metric(record, metric_name)
                if value is not None:
                    values.setdefault(metric_name, []).append(value)
            raw_ref = (
                _value(record, "log_uri")
                or _value(record, "log_path")
                or _value(record, "run_id")
            )
            if raw_ref:
                raw_refs.append(str(raw_ref))
        metrics = [
            EvaluationMetric(metric_name, sum(metric_values) / len(metric_values))
            for metric_name, metric_values in values.items()
            if metric_values
        ]
        artifacts = [
            EvaluationArtifact(
                artifact_type="inspect_run_reference",
                uri=raw_refs[0] if len(raw_refs) == 1 else None,
                metadata={
                    "provider": "inspect_ai",
                    "statuses": statuses,
                    "run_reference_count": len(raw_refs),
                },
            )
        ]
        metadata = {
            "provider": "inspect_ai",
            "provider_version": self.descriptor.version,
            "runner_provenance": dict(provenance),
            "completion_status": "completed",
            "task_result_count": len(records),
        }
        return EvaluationResult(
            evaluation_id=str(uuid4()),
            execution_id=request.execution_id,
            evaluator_type="inspect_ai",
            evaluator_version=self.descriptor.version,
            metrics=metrics,
            metadata=metadata,
            provider_metadata=metadata,
            artifacts=artifacts,
            provider_descriptor_snapshot=request.provider_descriptor_snapshot,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def _inspect_version() -> str:
        try:
            return version("inspect-ai")
        except PackageNotFoundError:
            return "unavailable"

    @staticmethod
    def _require_installation() -> None:
        if InspectEvaluationRunner._inspect_version() == "unavailable":
            raise InspectRunnerError(
                "Inspect AI is unavailable. Install the ai-governance[inspect] extra."
            )


def _records(raw: object) -> tuple[object, ...]:
    samples = _value(raw, "samples")
    if isinstance(samples, Sequence) and not isinstance(samples, str | bytes | bytearray):
        return tuple(samples)
    if isinstance(raw, Sequence) and not isinstance(raw, str | bytes | bytearray):
        if not raw:
            raise InspectRunnerError("Inspect returned no task results.")
        records: list[object] = []
        for result in raw:
            samples = _value(result, "samples")
            if isinstance(samples, Sequence) and not isinstance(
                samples, str | bytes | bytearray
            ):
                records.extend(samples)
            else:
                records.append(result)
        return tuple(records)
    return (raw,)


def _value(record: object, key: str) -> object | None:
    if isinstance(record, Mapping):
        if key in record:
            return record[key]
        results = record.get("results")
    else:
        model_fields = getattr(type(record), "model_fields", None)
        if model_fields is not None and key not in model_fields:
            results = getattr(record, "results", None)
        elif hasattr(record, key):
            return getattr(record, key)
        else:
            results = getattr(record, "results", None)
    if isinstance(results, Sequence) and results:
        return _value(results[0], key)
    return None


def _number(value: object | None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolean(value: object | None, score: float | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "passed", "pass", "success"}
    return bool(score is not None and score > 0)


def _record_score(record: object) -> float | None:
    direct = _number(_value(record, "score"))
    if direct is not None:
        return direct
    scores = _value(record, "scores")
    if not isinstance(scores, Mapping) or not scores:
        return None
    score = next(iter(scores.values()))
    value = _value(score, "value")
    numeric = _number(value)
    if numeric is not None:
        return numeric
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"C", "CORRECT", "PASS", "PASSED", "TRUE"}:
            return 1.0
        if normalized in {"I", "INCORRECT", "FAIL", "FAILED", "FALSE"}:
            return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return None


def _inspect_sample_metric(record: object, metric_name: str) -> float | None:
    """Extract standard Inspect sample evidence without retaining content."""
    usage = _value(record, "model_usage")
    if metric_name in {"input_tokens", "output_tokens", "total_tokens"}:
        if not isinstance(usage, Mapping):
            return None
        return float(
            sum(
                _number(_value(model_usage, metric_name)) or 0.0
                for model_usage in usage.values()
            )
        )
    if metric_name == "wall_clock_duration_seconds":
        direct = _number(_value(record, "total_time"))
        if direct is not None:
            return direct
        events = _value(record, "events")
        if isinstance(events, Sequence):
            return float(
                sum(
                    _number(_value(_value(event, "output"), "time")) or 0.0
                    for event in events
                    if _value(event, "event") == "model"
                )
            )
    if metric_name == "tool_action_count":
        events = _value(record, "events")
        if isinstance(events, Sequence):
            return float(sum(1 for event in events if _value(event, "event") == "tool"))
        return 0.0
    return None


def _sample_result(
    record: object,
    *,
    index: int,
    provenance: Mapping[str, Any],
) -> EvaluationSampleResult:
    status = str(_value(record, "status") or "success").lower()
    error = _value(record, "error") or _value(record, "error_message")
    if error or status in {"error", "failed", "cancelled", "timeout"}:
        raise InspectRunnerError(
            f"Inspect evaluation reported {status}: {str(error or 'no details')[:300]}",
            category=_failure_category(error, status),
        )
    score = _record_score(record)
    metrics = [
        EvaluationMetric(
            "pass", 1.0 if _boolean(_value(record, "passed"), score) else 0.0
        )
    ]
    if score is not None:
        metrics.append(EvaluationMetric("score", score))
    aliases_by_metric = {
        "tool_action_count": ("tool_action_count", "tool_calls", "actions"),
        "input_tokens": ("input_tokens", "tokens_input"),
        "output_tokens": ("output_tokens", "tokens_output"),
        "total_tokens": ("total_tokens", "tokens"),
        "wall_clock_duration_seconds": (
            "wall_clock_duration_seconds",
            "duration_seconds",
            "duration",
        ),
        "estimated_model_cost": ("estimated_model_cost", "model_cost", "cost"),
    }
    for metric_name, aliases in aliases_by_metric.items():
        value = next(
            (
                numeric
                for alias in aliases
                if (numeric := _number(_value(record, alias))) is not None
            ),
            None,
        )
        if value is None:
            value = _inspect_sample_metric(record, metric_name)
        if value is not None:
            metrics.append(EvaluationMetric(metric_name, value))
    sample_id = str(_value(record, "id") or index)
    safe_events = _safe_observable_events(record)
    payload = {"schema_version": "1", "events": safe_events}
    artifacts = (
        EvaluationArtifact(
            artifact_type="observable_execution_events",
            payload=payload,
            metadata={
                "source": "inspect_ai",
                "schema_version": "1",
                "artifact_digest": _payload_digest(payload),
                "retention": "evaluation_result",
                "durable": True,
            },
        ),
    )
    return EvaluationSampleResult(
        sample_id=sample_id,
        metrics=tuple(metrics),
        metadata={
            "sample_status": status,
            "sample_index": index,
            "observable_event_count": len(safe_events),
        },
        artifacts=artifacts,
        provider_metadata={
            "provider": "inspect_ai",
            "runner_provenance": dict(provenance),
        },
    )


def _batch_artifacts(raw: object) -> list[EvaluationArtifact]:
    """Record raw log retention truthfully; local worker paths are not durable."""
    records = raw if isinstance(raw, Sequence) and not isinstance(raw, str | bytes) else (raw,)
    references = [
        str(reference)
        for record in records
        if (
            reference := _value(record, "log_uri")
            or _value(record, "log_path")
            or _value(record, "location")
        )
    ]
    if not references:
        return []
    reference = references[0]
    durable = reference.startswith(("s3://", "https://", "http://"))
    return [
        EvaluationArtifact(
            artifact_type="evaluation_provider_run_reference",
            uri=reference,
            metadata={
                "retention": "provider_default" if durable else "worker_local",
                "durable": durable,
                "retrievable_after_worker_restart": durable,
            },
        )
    ]


def _safe_observable_events(record: object) -> list[dict[str, object]]:
    """Project Inspect events to safe observable facts before persistence.

    Raw model output, tool arguments/results, prompts and hidden reasoning are
    never retained.  When a provider emits them, only a SHA-256 digest remains.
    """
    raw_events = _value(record, "events")
    if not isinstance(raw_events, Sequence) or isinstance(raw_events, str | bytes):
        return []
    safe: list[dict[str, object]] = []
    for index, event in enumerate(raw_events):
        kind = str(
            _value(event, "event") or _value(event, "event_type") or _value(event, "type") or "unknown"
        ).lower()
        item: dict[str, object] = {"sequence": index, "kind": kind}
        if kind in {"tool", "tool_call", "tool_result"}:
            item["tool"] = str(
                _value(event, "tool") or _value(event, "tool_name") or "unknown"
            )
            arguments = _value(event, "arguments") or _value(event, "input")
            result = _value(event, "result") or _value(event, "output")
            if arguments is not None:
                item["arguments_digest"] = _payload_digest(arguments)
            if result is not None:
                item["response_digest"] = _payload_digest(result)
        elif kind in {"error", "timeout", "failure"}:
            item["error_class"] = "timeout" if kind == "timeout" else "provider_error"
        elif kind in {"model", "model_call", "generate"}:
            model = _value(event, "model")
            if model is not None:
                item["model"] = str(model)
            output = _value(event, "output")
            duration = _number(_value(output, "time")) if output is not None else None
            if duration is not None:
                item["duration_seconds"] = duration
        safe.append(item)
    return safe


def _payload_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _dataset_version(request: EvaluationRequest) -> str | None:
    value = request.dataset.metadata.get("dataset_version")
    if value is not None:
        return str(value)
    if request.execution.dataset_refs:
        reference = request.execution.dataset_refs[0]
        _, separator, dataset_version = reference.rpartition(":")
        if separator and dataset_version:
            return dataset_version
    return None


def _failure_category(error: object | None, status: str) -> str:
    text = f"{status} {error or ''}".lower()
    if "model" in text or "provider" in text or "api" in text:
        return "model_failure"
    if "solver" in text or "scaffold" in text or "tool" in text:
        return "scaffold_failure"
    if "timeout" in text or "process" in text or "infrastructure" in text:
        return "infrastructure_failure"
    return "evaluation_runner_failure"


def _requires_unsupported_openai_tool_transport(config: InspectRunnerConfig) -> bool:
    """Identify the known Chat Completions tool limitation conservatively.

    The current adapter delegates OpenAI GPT-5 calls to Inspect's Chat
    Completions transport. That transport rejected the combination of GPT-5
    reasoning and function tools in the live validation. A configuration must
    explicitly declare ``requires_tools`` so a generic custom solver is never
    guessed to have capabilities it did not declare.
    """
    return config.requires_tools and config.model.lower().startswith("openai/gpt-5")


def _validate_supported_tool_transport(config: InspectRunnerConfig) -> None:
    """Fail a known unsupported combination before a worker receives it."""
    if _requires_unsupported_openai_tool_transport(config):
        raise InspectRunnerError(
            "The current Inspect adapter cannot run OpenAI GPT-5 tool scaffolds "
            "through its Chat Completions transport. Choose a supported tool-capable "
            "model and transport before submitting the job.",
            category="model_capability_failure",
        )


def _resolve_solver(config: InspectRunnerConfig) -> object:
    """Build an Inspect solver from a stable built-in or qualified identifier."""
    module_name, separator, attribute = config.solver.partition(":")
    if not separator:
        module_name, attribute = "inspect_ai.solver", module_name
    allowed_modules = ("inspect_ai.", "ai_governance.inspect_tasks")
    if not module_name.startswith(allowed_modules) or not attribute:
        raise InspectRunnerError(
            "Inspect solver identifiers must be built-in Inspect or packaged "
            "ai_governance.inspect_tasks import paths.",
            category="scaffold_failure",
        )
    try:
        factory = getattr(import_module(module_name), attribute)
    except (AttributeError, ImportError) as exc:
        raise InspectRunnerError(
            f"Inspect solver '{config.solver}' is unavailable.",
            category="scaffold_failure",
        ) from exc
    if not callable(factory):
        raise InspectRunnerError(
            f"Inspect solver '{config.solver}' is not callable.",
            category="scaffold_failure",
        )
    try:
        return factory(**dict(config.solver_config))
    except (TypeError, ValueError) as exc:
        raise InspectRunnerError(
            f"Inspect solver '{config.solver}' rejected its configuration.",
            category="scaffold_failure",
        ) from exc


def _resolve_task(identifier: str) -> object:
    """Resolve a packaged task identically in API and worker processes."""
    module_name, separator, attribute = identifier.partition(":")
    if not separator or not module_name or not attribute:
        raise InspectRunnerError(
            f"Inspect task '{identifier}' is not a packaged task identifier.",
            category="task_definition_failure",
        )
    try:
        factory = getattr(import_module(module_name), attribute)
    except (AttributeError, ImportError) as exc:
        raise InspectRunnerError(
            f"Inspect task '{identifier}' is unavailable in this runtime.",
            category="task_definition_failure",
        ) from exc
    if not callable(factory):
        raise InspectRunnerError(
            f"Inspect task '{identifier}' is not callable.",
            category="task_definition_failure",
        )
    try:
        return factory()
    except (TypeError, ValueError) as exc:
        raise InspectRunnerError(
            f"Inspect task '{identifier}' could not be constructed.",
            category="task_definition_failure",
        ) from exc
