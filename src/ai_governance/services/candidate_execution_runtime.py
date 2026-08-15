"""Candidate-model execution boundary for governed experiments.

This module deliberately sits between immutable candidate resolution and
evaluator invocation.  Evaluators receive persisted ``WorkflowExecution``
evidence; they never reconstruct a prompt, model, connection, or dataset item.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol

from ai_governance.domain.datasets import Dataset
from ai_governance.domain.experiments import Experiment, ExperimentCandidate
from ai_governance.domain.models import Model, runtime_model_provider_key
from ai_governance.domain.prompts import Prompt
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.events import EventPublisher, ResourceLifecycleEvent
from ai_governance.repositories.dataset_repository import DatasetRepository
from ai_governance.repositories.model_repository import ModelRepository
from ai_governance.repositories.prompt_repository import PromptRepository
from ai_governance.services.dataset_item_reader import (
    DatasetItem,
    DatasetItemReadError,
    DatasetItemReader,
)
from ai_governance.services.replay_execution import ReplayExecutionStore
from ai_governance.services.runtime_connection_service import RuntimeConnectionService
from ai_governance.tenancy.domain import TenantContext


LOGGER = logging.getLogger(__name__)
_DEFAULT_MODEL_RUNTIME_TIMEOUT_SECONDS = 60.0


class CandidateExecutionError(Exception):
    """A safe, operator-actionable candidate execution failure."""


class ModelRuntimeAdapterUnavailableError(CandidateExecutionError):
    """Raised when OSS has no adapter for a managed model provider."""


@dataclass(frozen=True)
class ModelRuntimeRequest:
    """The minimum secret-bearing request passed only to a runtime adapter."""

    provider: str
    model_identifier: str
    prompt: str
    parameters: Mapping[str, Any]
    connection_config: Mapping[str, Any]


@dataclass(frozen=True)
class RuntimeExecutionResult:
    """Secret-free evidence returned by a model runtime invocation."""

    output: str
    provider_request_id: str | None = None
    model_identifier: str | None = None
    resolved_parameters: Mapping[str, Any] | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    error: str | None = None


class ModelRuntimeAdapter(Protocol):
    """SPI for invoking one managed-model provider without service coupling."""

    def supports(self, provider: str) -> bool: ...

    def invoke(self, request: ModelRuntimeRequest) -> RuntimeExecutionResult: ...


class ModelRuntimeAdapterRegistry:
    """Resolve runtime adapters by managed model provider."""

    def __init__(self, adapters: Sequence[ModelRuntimeAdapter] = ()) -> None:
        self._adapters = list(adapters)

    def register(self, adapter: ModelRuntimeAdapter) -> None:
        self._adapters.append(adapter)

    def resolve(self, provider: str) -> ModelRuntimeAdapter:
        for adapter in self._adapters:
            if adapter.supports(provider):
                return adapter
        raise ModelRuntimeAdapterUnavailableError(
            f"No OSS candidate runtime adapter is available for model provider '{provider}'."
        )


class OpenAIModelRuntimeAdapter:
    """OSS adapter for OpenAI and OpenAI-compatible runtime connections."""

    def supports(self, provider: str) -> bool:
        return runtime_model_provider_key(provider) in {"openai", "custom"}

    def invoke(self, request: ModelRuntimeRequest) -> RuntimeExecutionResult:
        api_key = str(request.connection_config.get("api_key") or "").strip()
        if not api_key:
            raise CandidateExecutionError(
                "The runtime connection does not resolve an API key for candidate execution."
            )
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=api_key,
                base_url=_optional_string(request.connection_config.get("base_url")),
                organization=_optional_string(request.connection_config.get("organization")),
                timeout=_DEFAULT_MODEL_RUNTIME_TIMEOUT_SECONDS,
                max_retries=0,
            )
            LOGGER.info(
                "model_runtime_provider_invocation_started provider=%s model_identifier=%s timeout_seconds=%s",
                request.provider,
                request.model_identifier,
                _DEFAULT_MODEL_RUNTIME_TIMEOUT_SECONDS,
            )
            started = perf_counter()
            response = client.chat.completions.create(**_openai_request_arguments(request))
            latency_ms = int((perf_counter() - started) * 1000)
        except CandidateExecutionError:
            raise
        except Exception as exc:
            details = _safe_provider_error_details(exc)
            LOGGER.warning(
                "candidate_model_invocation_failed provider=%s model_identifier=%s "
                "error_type=%s provider_status_code=%s provider_error_code=%s "
                "provider_error_type=%s provider_parameter=%s provider_request_id=%s",
                request.provider,
                request.model_identifier,
                type(exc).__name__,
                details["status_code"],
                details["code"],
                details["type"],
                details["parameter"],
                details["request_id"],
            )
            raise CandidateExecutionError(_safe_provider_failure_reason(details)) from exc

        LOGGER.info(
            "model_runtime_provider_invocation_completed provider=%s model_identifier=%s latency_ms=%s",
            request.provider,
            request.model_identifier,
            latency_ms,
        )

        choice = response.choices[0] if response.choices else None
        output = str(choice.message.content or "") if choice is not None else ""
        if not output.strip():
            raise CandidateExecutionError("The model runtime returned no candidate output.")
        usage = response.usage
        return RuntimeExecutionResult(
            output=output,
            provider_request_id=_optional_string(getattr(response, "_request_id", None)),
            model_identifier=str(getattr(response, "model", None) or request.model_identifier),
            resolved_parameters=dict(request.parameters),
            latency_ms=latency_ms,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            finish_reason=(str(choice.finish_reason) if choice and choice.finish_reason else None),
        )


class AnthropicModelRuntimeAdapter:
    """OSS adapter for Anthropic Messages API runtime connections."""

    def supports(self, provider: str) -> bool:
        return runtime_model_provider_key(provider) == "anthropic"

    def invoke(self, request: ModelRuntimeRequest) -> RuntimeExecutionResult:
        api_key = str(request.connection_config.get("api_key") or "").strip()
        if not api_key:
            raise CandidateExecutionError(
                "The runtime connection does not resolve an API key for candidate execution."
            )
        try:
            from anthropic import Anthropic

            client = Anthropic(
                api_key=api_key,
                base_url=_optional_string(request.connection_config.get("base_url")),
                timeout=_DEFAULT_MODEL_RUNTIME_TIMEOUT_SECONDS,
                max_retries=0,
            )
            LOGGER.info(
                "model_runtime_provider_invocation_started provider=%s model_identifier=%s timeout_seconds=%s",
                request.provider,
                request.model_identifier,
                _DEFAULT_MODEL_RUNTIME_TIMEOUT_SECONDS,
            )
            started = perf_counter()
            response = client.messages.create(**_anthropic_request_arguments(request))
            latency_ms = int((perf_counter() - started) * 1000)
        except CandidateExecutionError:
            raise
        except Exception as exc:
            details = _safe_provider_error_details(exc)
            LOGGER.warning(
                "candidate_model_invocation_failed provider=%s model_identifier=%s "
                "error_type=%s provider_status_code=%s provider_error_code=%s "
                "provider_error_type=%s provider_parameter=%s provider_request_id=%s",
                request.provider,
                request.model_identifier,
                type(exc).__name__,
                details["status_code"],
                details["code"],
                details["type"],
                details["parameter"],
                details["request_id"],
            )
            raise CandidateExecutionError(_safe_provider_failure_reason(details)) from exc

        LOGGER.info(
            "model_runtime_provider_invocation_completed provider=%s model_identifier=%s latency_ms=%s",
            request.provider,
            request.model_identifier,
            latency_ms,
        )
        output = _anthropic_output_text(getattr(response, "content", ()))
        if not output.strip():
            raise CandidateExecutionError("The model runtime returned no candidate output.")
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        return RuntimeExecutionResult(
            output=output,
            provider_request_id=_optional_string(getattr(response, "_request_id", None)),
            model_identifier=str(getattr(response, "model", None) or request.model_identifier),
            resolved_parameters=dict(request.parameters),
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(input_tokens + output_tokens if isinstance(input_tokens, int) and isinstance(output_tokens, int) else None),
            finish_reason=_optional_string(getattr(response, "stop_reason", None)),
        )


class CandidateExecutionRuntime:
    """Resolve and invoke a candidate over its immutable dataset records."""

    def __init__(
        self,
        *,
        prompt_repository: PromptRepository,
        model_repository: ModelRepository,
        dataset_repository: DatasetRepository,
        runtime_connection_service: RuntimeConnectionService,
        dataset_item_reader: DatasetItemReader,
        adapter_registry: ModelRuntimeAdapterRegistry,
        execution_store: ReplayExecutionStore,
        event_publisher: EventPublisher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._prompt_repository = prompt_repository
        self._model_repository = model_repository
        self._dataset_repository = dataset_repository
        self._runtime_connection_service = runtime_connection_service
        self._dataset_item_reader = dataset_item_reader
        self._adapter_registry = adapter_registry
        self._execution_store = execution_store
        self._event_publisher = event_publisher
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        *,
        experiment: Experiment,
        candidate: ExperimentCandidate,
        run_id: str,
        context: TenantContext,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[WorkflowExecution, ...]:
        """Persist one execution per immutable dataset item before evaluation."""
        LOGGER.info(
            "candidate_execution_started experiment_id=%s candidate_id=%s run_id=%s",
            experiment.experiment_id,
            candidate.candidate_id,
            run_id,
        )
        try:
            prompt, model, dataset = self._resolve_assets(candidate, context)
            connection_id = str(candidate.metadata.get("runtime_connection_id") or "").strip()
            if not connection_id:
                raise CandidateExecutionError(
                    "Candidate execution requires an active runtime connection."
                )
            _, connection_config = self._runtime_connection_service.resolve_runtime_config(
                connection_id, model.provider, context
            )
            adapter = self._adapter_registry.resolve(model.provider)
            items = self._dataset_item_reader.read_items(dataset, context)
        except Exception as exc:
            LOGGER.warning(
                "candidate_execution_resolution_failed experiment_id=%s candidate_id=%s run_id=%s error_type=%s failure_reason=%s",
                experiment.experiment_id,
                candidate.candidate_id,
                run_id,
                type(exc).__name__,
                _safe_resolution_failure_reason(exc),
            )
            raise _as_candidate_execution_error(exc) from exc
        LOGGER.info(
            "candidate_execution_inputs_resolved experiment_id=%s candidate_id=%s run_id=%s model_provider=%s model_id=%s dataset_id=%s dataset_version=%s item_count=%s",
            experiment.experiment_id,
            candidate.candidate_id,
            run_id,
            model.provider,
            model.model_id,
            dataset.dataset_id,
            dataset.version,
            len(items),
        )
        if progress_callback is not None:
            progress_callback(len(items), 0)
        executions: list[WorkflowExecution] = []
        for item in items:
            execution_id = f"{run_id}:{item.item_id}"
            self._publish_lifecycle_event(
                state="started",
                execution_id=execution_id,
                experiment=experiment,
                candidate=candidate,
                item=item,
                model=model,
                context=context,
            )
            LOGGER.info(
                "candidate_model_invocation_started run_id=%s execution_id=%s candidate_id=%s dataset_item_id=%s model_provider=%s model_identifier=%s",
                run_id,
                execution_id,
                candidate.candidate_id,
                item.item_id,
                model.provider,
                model.runtime_model_identifier,
            )
            try:
                rendered_prompt = _render_prompt(prompt, item)
                result = adapter.invoke(
                    ModelRuntimeRequest(
                        provider=model.provider,
                        model_identifier=model.runtime_model_identifier,
                        prompt=rendered_prompt,
                        parameters=_candidate_runtime_parameters(candidate, model),
                        connection_config=connection_config,
                    )
                )
                if result.error:
                    raise CandidateExecutionError("The model runtime returned an execution error.")
                execution = self._completed_execution(
                    experiment, candidate, dataset, item, execution_id, result, context
                )
            except Exception as exc:
                failed = self._failed_execution(
                    experiment, candidate, dataset, item, execution_id, exc, context
                )
                self._execution_store.save(failed)
                self._publish_lifecycle_event(
                    state="failed",
                    execution_id=execution_id,
                    experiment=experiment,
                    candidate=candidate,
                    item=item,
                    model=model,
                    context=context,
                )
                LOGGER.warning(
                    "candidate_execution_failed run_id=%s execution_id=%s candidate_id=%s dataset_item_id=%s error_type=%s failure_reason=%s",
                    run_id,
                    execution_id,
                    candidate.candidate_id,
                    item.item_id,
                    type(exc).__name__,
                    _safe_execution_failure_reason(exc),
                )
                raise _as_candidate_execution_error(exc) from exc
            self._execution_store.save(execution)
            self._publish_lifecycle_event(
                state="completed",
                execution_id=execution_id,
                experiment=experiment,
                candidate=candidate,
                item=item,
                model=model,
                context=context,
                runtime_result=result,
            )
            LOGGER.info(
                "candidate_execution_completed run_id=%s execution_id=%s candidate_id=%s dataset_item_id=%s latency_ms=%s input_tokens=%s output_tokens=%s total_tokens=%s finish_reason=%s provider_request_id=%s",
                run_id,
                execution_id,
                candidate.candidate_id,
                item.item_id,
                result.latency_ms,
                result.input_tokens,
                result.output_tokens,
                result.total_tokens,
                result.finish_reason,
                result.provider_request_id,
            )
            executions.append(execution)
            if progress_callback is not None:
                progress_callback(len(items), len(executions))
        LOGGER.info(
            "candidate_execution_finished experiment_id=%s candidate_id=%s run_id=%s completed_item_count=%s",
            experiment.experiment_id,
            candidate.candidate_id,
            run_id,
            len(executions),
        )
        return tuple(executions)

    def _publish_lifecycle_event(
        self,
        *,
        state: str,
        execution_id: str,
        experiment: Experiment,
        candidate: ExperimentCandidate,
        item: DatasetItem,
        model: Model,
        context: TenantContext,
        runtime_result: RuntimeExecutionResult | None = None,
    ) -> None:
        """Notify extensions without exposing prompt, input, output, or secrets."""
        if self._event_publisher is None:
            return
        payload: dict[str, Any] = {
            "experiment_id": experiment.experiment_id,
            "candidate_id": candidate.candidate_id,
            "dataset_item_id": item.item_id,
            "model_provider": model.provider,
            "model_id": model.model_id,
        }
        if runtime_result is not None:
            payload.update(
                {
                    "latency_ms": runtime_result.latency_ms,
                    "input_tokens": runtime_result.input_tokens,
                    "output_tokens": runtime_result.output_tokens,
                    "total_tokens": runtime_result.total_tokens,
                    "finish_reason": runtime_result.finish_reason,
                    "provider_request_id": runtime_result.provider_request_id,
                }
            )
        asyncio.run(
            self._event_publisher.publish(
                ResourceLifecycleEvent(
                    tenant={
                        "organization_id": context.organization_id,
                        "project_id": context.project_id or "",
                    },
                    resource_kind="candidate_execution",
                    resource_id=execution_id,
                    state=state,
                    payload=payload,
                )
            )
        )

    def _resolve_assets(
        self, candidate: ExperimentCandidate, context: TenantContext
    ) -> tuple[Prompt, Model, Dataset]:
        organization_id, project_id = context.organization_id, context.project_id or ""
        prompt = self._prompt_repository.find_by_id(candidate.prompt_id, organization_id, project_id)
        if prompt is None or prompt.version != candidate.prompt_version:
            raise CandidateExecutionError("Candidate references an unknown prompt version.")
        if prompt.template is None:
            raise CandidateExecutionError("Candidate prompt content is unavailable for execution.")
        model = self._model_repository.find_by_id(candidate.model_id, organization_id, project_id)
        if model is None or model.version != candidate.model_version:
            raise CandidateExecutionError("Candidate references an unknown model version.")
        dataset = self._dataset_repository.find_by_id(candidate.dataset_id)
        if dataset is None or dataset.version != candidate.dataset_version:
            raise CandidateExecutionError("Candidate references an unknown dataset version.")
        if dataset.organization_id != organization_id or dataset.project_id != project_id:
            raise CandidateExecutionError("Candidate dataset is not available in the current tenant scope.")
        return prompt, model, dataset

    def _completed_execution(
        self,
        experiment: Experiment,
        candidate: ExperimentCandidate,
        dataset: Dataset,
        item: DatasetItem,
        execution_id: str,
        result: RuntimeExecutionResult,
        context: TenantContext,
    ) -> WorkflowExecution:
        now = self._clock()
        evidence = {
            "provider_request_id": result.provider_request_id,
            "model_identifier": result.model_identifier,
            "resolved_parameters": dict(result.resolved_parameters or {}),
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
            "finish_reason": result.finish_reason,
            "error": result.error,
        }
        return WorkflowExecution(
            workflow_id=experiment.experiment_id,
            execution_id=execution_id,
            workflow_name=experiment.name,
            workflow_version="candidate-execution-v1",
            execution_status="COMPLETED",
            input={"input": item.input_text, "dataset_item_id": item.item_id},
            final_state={"answer": result.output, "context": item.context_text},
            events=[
                {"type": "CANDIDATE_EXECUTION_COMPLETED", "at": now.isoformat()},
            ],
            organization_id=context.organization_id,
            project_id=context.project_id or "",
            execution_adapter="candidate_runtime",
            prompt_refs=[f"{candidate.prompt_id}:{candidate.prompt_version}"],
            model_refs=[f"{candidate.model_id}:{candidate.model_version}"],
            dataset_refs=[f"{dataset.dataset_id}:{dataset.version}"],
            runtime_parameters=dict(evidence["resolved_parameters"]),
            metadata={
                "experiment_id": experiment.experiment_id,
                "candidate_id": candidate.candidate_id,
                "dataset_item_id": item.item_id,
                "dataset_item_metadata": dict(item.metadata),
                "runtime_evidence": evidence,
            },
            created_at=now,
        )

    def _failed_execution(
        self,
        experiment: Experiment,
        candidate: ExperimentCandidate,
        dataset: Dataset,
        item: DatasetItem,
        execution_id: str,
        error: Exception,
        context: TenantContext,
    ) -> WorkflowExecution:
        now = self._clock()
        return WorkflowExecution(
            workflow_id=experiment.experiment_id,
            execution_id=execution_id,
            workflow_name=experiment.name,
            workflow_version="candidate-execution-v1",
            execution_status="FAILED",
            input={"input": item.input_text, "dataset_item_id": item.item_id},
            final_state={},
            events=[{"type": "CANDIDATE_EXECUTION_FAILED", "at": now.isoformat()}],
            organization_id=context.organization_id,
            project_id=context.project_id or "",
            execution_adapter="candidate_runtime",
            prompt_refs=[f"{candidate.prompt_id}:{candidate.prompt_version}"],
            model_refs=[f"{candidate.model_id}:{candidate.model_version}"],
            dataset_refs=[f"{dataset.dataset_id}:{dataset.version}"],
            metadata={
                "experiment_id": experiment.experiment_id,
                "candidate_id": candidate.candidate_id,
                "dataset_item_id": item.item_id,
                "failure_reason": _safe_execution_failure_reason(error),
            },
            created_at=now,
        )


def _render_prompt(prompt: Prompt, item: DatasetItem) -> str:
    values = {**dict(item.variables), "input": item.input_text, "context": item.context_text}
    missing = [name for name in prompt.variables if not values.get(name)]
    if missing:
        raise CandidateExecutionError(
            "Dataset item is missing prompt variables: " + ", ".join(sorted(missing)) + "."
        )
    try:
        return (prompt.template or "").format_map(values)
    except (KeyError, ValueError, IndexError) as exc:
        raise CandidateExecutionError("Candidate prompt could not be rendered for a dataset item.") from exc


def _candidate_runtime_parameters(
    candidate: ExperimentCandidate, model: Model
) -> dict[str, Any]:
    """Return only explicitly governed candidate overrides for a new profile.

    Candidates created before capability snapshots retain their historical
    parameter semantics and are therefore treated as explicit legacy records.
    """

    parameters = dict(model.parameters)
    overrides = candidate.metadata.get("runtime_parameter_overrides")
    names = (
        {str(value) for value in overrides}
        if isinstance(overrides, list)
        else {"temperature", "top_p", "max_tokens"}
    )
    values = {
        "temperature": candidate.temperature,
        "top_p": candidate.top_p,
        "max_tokens": candidate.max_tokens,
    }
    parameters.update({name: values[name] for name in names if name in values})
    return parameters


def _as_candidate_execution_error(error: Exception) -> CandidateExecutionError:
    if isinstance(error, CandidateExecutionError):
        return error
    if isinstance(error, DatasetItemReadError):
        return CandidateExecutionError(" ".join(str(error).split())[:500])
    return CandidateExecutionError("Candidate execution failed. Inspect secure runtime logs for details.")


def _safe_execution_failure_reason(error: Exception) -> str:
    if isinstance(error, CandidateExecutionError):
        return " ".join(str(error).split())[:500]
    return "Candidate execution failed. Inspect secure runtime logs for details."


def _safe_resolution_failure_reason(error: Exception) -> str:
    if isinstance(error, (CandidateExecutionError, DatasetItemReadError)):
        return " ".join(str(error).split())[:500]
    return "Candidate execution setup failed. Inspect secure runtime logs for details."


def _openai_request_arguments(request: ModelRuntimeRequest) -> dict[str, Any]:
    """Translate generic governed parameters to the selected OpenAI endpoint."""

    arguments: dict[str, Any] = {
        "model": request.model_identifier,
        "messages": [{"role": "user", "content": request.prompt}],
    }
    for name, value in (
        ("temperature", _number(request.parameters.get("temperature"))),
        ("top_p", _number(request.parameters.get("top_p"))),
    ):
        if value is not None:
            arguments[name] = value
    max_tokens = _integer(
        request.parameters.get("max_output_tokens", request.parameters.get("max_tokens"))
    )
    if max_tokens is not None:
        # The OpenAI API supersedes max_tokens with max_completion_tokens.
        # Keep the original parameter for compatible third-party endpoints.
        key = (
            "max_completion_tokens"
            if runtime_model_provider_key(request.provider) == "openai"
            else "max_tokens"
        )
        arguments[key] = max_tokens
    return arguments


def _anthropic_request_arguments(request: ModelRuntimeRequest) -> dict[str, Any]:
    """Translate portable controls to the Anthropic Messages API contract."""

    max_tokens = _integer(
        request.parameters.get("max_output_tokens", request.parameters.get("max_tokens"))
    )
    if max_tokens is None:
        raise CandidateExecutionError(
            "The Anthropic runtime requires max output tokens in the managed model or candidate configuration."
        )
    arguments: dict[str, Any] = {
        "model": request.model_identifier,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": request.prompt}],
    }
    for name, value in (
        ("temperature", _number(request.parameters.get("temperature"))),
        ("top_p", _number(request.parameters.get("top_p"))),
    ):
        if value is not None:
            arguments[name] = value
    return arguments


def _anthropic_output_text(content: Any) -> str:
    return "".join(
        str(getattr(block, "text", ""))
        for block in content
        if getattr(block, "type", None) == "text"
    )


_SAFE_PROVIDER_PARAMETERS = frozenset(
    {
        "model",
        "messages",
        "temperature",
        "top_p",
        "max_tokens",
        "max_completion_tokens",
    }
)


def _safe_provider_error_details(error: Exception) -> dict[str, str | int | None]:
    """Extract stable provider diagnostics without logging message/body content."""

    payload = getattr(error, "body", None)
    if isinstance(payload, Mapping):
        nested = payload.get("error")
        if isinstance(nested, Mapping):
            payload = nested
    else:
        payload = {}

    parameter = _safe_error_token(
        getattr(error, "param", None) or payload.get("param")
    )
    return {
        "status_code": _safe_status_code(getattr(error, "status_code", None)),
        "code": _safe_error_token(getattr(error, "code", None) or payload.get("code")),
        "type": _safe_error_token(getattr(error, "type", None) or payload.get("type")),
        "parameter": parameter if parameter in _SAFE_PROVIDER_PARAMETERS else None,
        "request_id": _safe_error_token(
            getattr(error, "request_id", None) or payload.get("request_id")
        ),
    }


def _safe_provider_failure_reason(details: Mapping[str, str | int | None]) -> str:
    parameter = details.get("parameter")
    if isinstance(parameter, str):
        return f"The model runtime rejected the '{parameter}' request parameter."
    status_code = details.get("status_code")
    if status_code in {401, 403}:
        return "The model runtime rejected the runtime-connection credentials."
    if status_code == 404:
        return "The model runtime could not resolve the registered model identifier."
    if status_code == 429:
        return "The model runtime rate limit was reached."
    return "The model runtime invocation failed. Inspect secure runtime logs for provider details."


def _safe_error_token(value: object) -> str | None:
    result = str(value or "").strip()
    return result if re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", result) else None


def _safe_status_code(value: object) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if 100 <= result <= 599 else None


def _optional_string(value: object) -> str | None:
    result = str(value or "").strip()
    return result or None


def _number(value: object) -> float | None:
    return float(value) if value is not None else None


def _integer(value: object) -> int | None:
    return int(value) if value is not None else None
