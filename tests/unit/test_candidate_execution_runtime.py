from __future__ import annotations

import sys
from datetime import UTC, datetime
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ai_governance.domain.datasets import Dataset, DatasetStatus
from ai_governance.domain.experiments import Experiment, ExperimentCandidate, ExperimentStatus
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.events import EventPublisher, ResourceLifecycleEvent
from ai_governance.repositories.in_memory_dataset_repository import InMemoryDatasetRepository
from ai_governance.repositories.in_memory_model_repository import InMemoryModelRepository
from ai_governance.repositories.in_memory_prompt_repository import InMemoryPromptRepository
from ai_governance.services.candidate_execution_runtime import (
    CandidateExecutionError,
    CandidateExecutionRuntime,
    ModelRuntimeAdapterRegistry,
    ModelRuntimeRequest,
    OpenAIModelRuntimeAdapter,
    RuntimeExecutionResult,
)
from ai_governance.services.dataset_item_reader import DatasetItem
from ai_governance.services.replay_execution_discovery import InMemoryReplaySourceResolver
from ai_governance.tenancy.domain import TenantContext


_NOW = datetime(2026, 8, 11, tzinfo=UTC)
_CONTEXT = TenantContext("org_default", "project_default", "test-user", "request-1")


class _Reader:
    def read_items(self, dataset: Dataset, context: TenantContext) -> tuple[DatasetItem, ...]:
        return (
            DatasetItem(
                item_id="dataset-1:1",
                input_text="Where is my order?",
                context_text="Order 123 is in transit.",
                variables={"question": "Where is my order?", "context": "Order 123 is in transit."},
                metadata={"dataset_record_index": 1},
            ),
            DatasetItem(
                item_id="dataset-1:2",
                input_text="Can I change my address?",
                context_text="Address changes are available before dispatch.",
                variables={"question": "Can I change my address?", "context": "Address changes are available before dispatch."},
                metadata={"dataset_record_index": 2},
            ),
        )


class _RuntimeConnectionService:
    def resolve_runtime_config(self, connection_id: str, provider: str, context: TenantContext):
        assert connection_id == "connection-1"
        assert provider == "openai"
        assert context == _CONTEXT
        return object(), {"api_key": "must-not-be-persisted"}


class _Adapter:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.requests: list[ModelRuntimeRequest] = []

    def supports(self, provider: str) -> bool:
        return provider == "openai"

    def invoke(self, request: ModelRuntimeRequest) -> RuntimeExecutionResult:
        self.requests.append(request)
        if self.failure:
            raise self.failure
        return RuntimeExecutionResult(
            output=f"Answer: {request.prompt}",
            provider_request_id="provider-request-1",
            model_identifier=request.model_identifier,
            resolved_parameters=dict(request.parameters),
            latency_ms=42,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            finish_reason="stop",
        )


def test_candidate_runtime_persists_exact_execution_evidence_before_evaluation() -> None:
    runtime, store, adapter = _runtime(_Adapter())

    executions = runtime.execute(
        experiment=_experiment(), candidate=_candidate(), run_id="run-1", context=_CONTEXT
    )

    assert [execution.execution_id for execution in executions] == [
        "run-1:dataset-1:1",
        "run-1:dataset-1:2",
    ]
    assert adapter.requests[0].prompt == "Use Order 123 is in transit. to answer Where is my order?."
    stored = store.get_execution("run-1:dataset-1:1", _CONTEXT)
    assert stored is not None
    assert stored.input["input"] == "Where is my order?"
    assert stored.final_state["answer"].startswith("Answer:")
    assert stored.metadata["runtime_evidence"]["total_tokens"] == 15
    assert "api_key" not in str(stored.metadata)


def test_candidate_runtime_reports_persisted_item_progress() -> None:
    runtime, _store, _adapter = _runtime(_Adapter())
    progress: list[tuple[int, int]] = []

    runtime.execute(
        experiment=_experiment(),
        candidate=_candidate(),
        run_id="run-1",
        context=_CONTEXT,
        progress_callback=lambda total, completed: progress.append((total, completed)),
    )

    assert progress == [(2, 0), (2, 1), (2, 2)]


def test_candidate_runtime_invokes_the_immutable_provider_model_id() -> None:
    runtime, _store, adapter = _runtime(_Adapter(), provider_model_id="gpt-4.1-mini")

    runtime.execute(
        experiment=_experiment(), candidate=_candidate(), run_id="run-1", context=_CONTEXT
    )

    assert adapter.requests[0].model_identifier == "gpt-4.1-mini"


def test_candidate_runtime_persists_failed_execution_and_never_returns_empty_answer() -> None:
    runtime, store, _ = _runtime(_Adapter(CandidateExecutionError("Model unavailable.")))

    with pytest.raises(CandidateExecutionError, match="Model unavailable"):
        runtime.execute(
            experiment=_experiment(), candidate=_candidate(), run_id="run-1", context=_CONTEXT
        )

    failed = store.get_execution("run-1:dataset-1:1", _CONTEXT)
    assert failed is not None
    assert failed.execution_status == "FAILED"
    assert failed.final_state == {}
    assert failed.metadata["failure_reason"] == "Model unavailable."


def test_candidate_runtime_uses_provider_defaults_when_new_candidate_has_no_overrides() -> None:
    runtime, _store, adapter = _runtime(_Adapter())
    candidate = replace(
        _candidate(),
        metadata={"runtime_connection_id": "connection-1", "runtime_parameter_overrides": []},
    )

    runtime.execute(
        experiment=_experiment(), candidate=candidate, run_id="run-1", context=_CONTEXT
    )

    assert adapter.requests[0].parameters == {}


def test_candidate_runtime_logs_lifecycle_and_publishes_secret_free_events(
    caplog: pytest.LogCaptureFixture,
) -> None:
    publisher = EventPublisher()
    lifecycle_events: list[ResourceLifecycleEvent] = []
    publisher.subscribe(
        event_type=ResourceLifecycleEvent,
        handler=lifecycle_events.append,
        plugin_name="candidate-runtime-test",
    )
    runtime, _store, _adapter = _runtime(_Adapter(), event_publisher=publisher)

    with caplog.at_level("INFO", logger="ai_governance.services.candidate_execution_runtime"):
        runtime.execute(
            experiment=_experiment(), candidate=_candidate(), run_id="run-1", context=_CONTEXT
        )

    assert [event.state for event in lifecycle_events] == [
        "started",
        "completed",
        "started",
        "completed",
    ]
    assert lifecycle_events[1].payload["total_tokens"] == 15
    assert "api_key" not in str(lifecycle_events)
    assert "Where is my order?" not in caplog.text
    assert "candidate_execution_completed" in caplog.text


def test_openai_runtime_translates_governed_max_tokens_to_openai_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    client_options: dict[str, object] = {}

    class _Completions:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Answer"), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2, total_tokens=6),
                model="gpt-5.5",
                _request_id="req-test",
            )

    class _OpenAI:
        def __init__(self, **kwargs: object) -> None:
            client_options.update(kwargs)
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI))

    result = OpenAIModelRuntimeAdapter().invoke(
        ModelRuntimeRequest(
            provider="openai",
            model_identifier="gpt-5.5",
            prompt="Protected prompt content",
            parameters={"temperature": 0, "top_p": 1, "max_tokens": 1024},
            connection_config={"api_key": "secret"},
        )
    )

    assert result.output == "Answer"
    assert captured["max_completion_tokens"] == 1024
    assert "max_tokens" not in captured
    assert client_options["timeout"] == 60.0
    assert client_options["max_retries"] == 0


def test_openai_runtime_accepts_canonical_max_output_tokens_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Completions:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Answer"), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2, total_tokens=6),
                model="gpt-5.5",
                _request_id="req-test",
            )

    class _OpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI))

    OpenAIModelRuntimeAdapter().invoke(
        ModelRuntimeRequest(
            provider="openai",
            model_identifier="gpt-5.5",
            prompt="Protected prompt content",
            parameters={"max_output_tokens": 4096},
            connection_config={"api_key": "secret"},
        )
    )

    assert captured["max_completion_tokens"] == 4096


def test_openai_runtime_logs_safe_provider_parameter_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _BadRequest(Exception):
        status_code = 400
        code = "unsupported_parameter"
        type = "invalid_request_error"
        param = "max_completion_tokens"
        request_id = "req-provider"

    class _Completions:
        def create(self, **kwargs: object) -> None:
            raise _BadRequest()

    class _OpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI))
    request = ModelRuntimeRequest(
        provider="openai",
        model_identifier="gpt-5.5",
        prompt="Protected prompt content",
        parameters={"max_tokens": 1024},
        connection_config={"api_key": "secret"},
    )

    with caplog.at_level("WARNING", logger="ai_governance.services.candidate_execution_runtime"):
        with pytest.raises(CandidateExecutionError, match="max_completion_tokens"):
            OpenAIModelRuntimeAdapter().invoke(request)

    assert "provider_parameter=max_completion_tokens" in caplog.text
    assert "Protected prompt content" not in caplog.text
    assert "secret" not in caplog.text


def _runtime(
    adapter: _Adapter,
    event_publisher: EventPublisher | None = None,
    provider_model_id: str | None = None,
):
    prompts, models, datasets = InMemoryPromptRepository(), InMemoryModelRepository(), InMemoryDatasetRepository()
    prompts.save(
        Prompt(
            prompt_id="prompt-1", name="Support", version="v1", template="Use {context} to answer {question}.",
            variables=("question", "context"), created_at=_NOW, created_by="test", status=PromptStatus.ACTIVE,
        )
    )
    models.save(
        Model(
            model_id="model-1", provider="openai", model_name="gpt-test", version="v1", parameters={},
            cost=None, latency=None, context_window=128000, creator="test", created_at=_NOW, status=ModelStatus.ACTIVE,
            provider_model_id=provider_model_id,
        )
    )
    datasets.save(
        Dataset(
            dataset_id="dataset-1", name="Evaluation", version="v1", description="Test data", storage_uri="s3://bucket/data.jsonl",
            storage_type="S3", schema_version="1", record_count=2, checksum="checksum", creator="test", created_at=_NOW,
            status=DatasetStatus.FROZEN,
        )
    )
    store = InMemoryReplaySourceResolver()
    return (
        CandidateExecutionRuntime(
            prompt_repository=prompts,
            model_repository=models,
            dataset_repository=datasets,
            runtime_connection_service=_RuntimeConnectionService(),
            dataset_item_reader=_Reader(),
            adapter_registry=ModelRuntimeAdapterRegistry((adapter,)),
            execution_store=store,
            event_publisher=event_publisher,
            clock=lambda: _NOW,
        ),
        store,
        adapter,
    )


def _experiment() -> Experiment:
    return Experiment(
        experiment_id="experiment-1", name="Support benchmark", description="Compare candidates", owner="test",
        status=ExperimentStatus.RUNNING, created_at=_NOW, updated_at=_NOW,
    )


def _candidate() -> ExperimentCandidate:
    return ExperimentCandidate(
        candidate_id="candidate-1", experiment_id="experiment-1", name="candidate", prompt_id="prompt-1", prompt_version="v1",
        model_id="model-1", model_version="v1", dataset_id="dataset-1", dataset_version="v1", evaluation_provider="mock",
        temperature=0.0, top_p=1.0, max_tokens=100, metadata={"runtime_connection_id": "connection-1"}, created_at=_NOW,
    )
