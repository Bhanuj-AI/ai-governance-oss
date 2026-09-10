from __future__ import annotations

import ast
import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_governance.domain.experiments import ExperimentCandidate
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.providers.inspect_ai import (
    InspectEvaluationRunner,
    InspectRunnerConfig,
    InspectRunnerError,
)
from ai_governance.providers.inspect_ai.adapter import _resolve_solver
from ai_governance.providers.inspect_ai.provenance import configuration_provenance
from ai_governance.providers.provider_registry import EvaluationProviderRegistry
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.services.evaluation_api_service import (
    EvaluationApiService,
    EvaluationNotFoundError,
)
from ai_governance.services.experiment_api_service import ExperimentApiService
from ai_governance.tenancy.domain import TenantContext


def test_inspect_runner_invokes_adapter_and_normalizes_result() -> None:
    received: list[InspectRunnerConfig] = []
    runner = InspectEvaluationRunner(
        executor=lambda config: (
            received.append(config)
            or {
                "status": "success",
                "passed": True,
                "score": 0.9,
                "tool_calls": 3,
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
                "duration_seconds": 1.5,
                "model_cost": 0.002,
                "log_uri": "file:///tmp/inspect.eval",
            }
        )
    )

    result = runner.evaluate(
        _request(
            {
                "model": "openai/gpt-5-mini",
                "tasks": ["benchmarks.math:task"],
                "task_version": "2026-09-01",
                "solver": "basic_agent",
                "solver_config": {"max_steps": 4, "api_key": "never-persist"},
                "scorer": "exact",
                "scorer_version": "1",
                "task_limit": 2,
                "timeout_seconds": 30,
            }
        )
    )

    assert received[0].solver == "basic_agent"
    assert dict(received[0].solver_config) == {"max_steps": 4}
    assert {metric.metric_name: metric.metric_value for metric in result.metrics} == {
        "pass": 1.0,
        "score": 0.9,
        "tool_action_count": 3.0,
        "input_tokens": 11.0,
        "output_tokens": 7.0,
        "total_tokens": 18.0,
        "wall_clock_duration_seconds": 1.5,
        "estimated_model_cost": 0.002,
    }
    assert result.artifacts[0].uri == "file:///tmp/inspect.eval"
    provenance = result.provider_metadata["runner_provenance"]
    assert provenance["runner_type"] == "inspect_ai"
    assert provenance["solver_config_digest"].startswith("sha256:")
    assert provenance["configuration_fingerprint"].startswith("sha256:")
    assert "never-persist" not in str(result.provider_metadata)


def test_inspect_configuration_fingerprint_is_deterministic_and_changes_for_solver() -> (
    None
):
    baseline = InspectRunnerConfig.from_mapping(
        {
            "model": "model-a",
            "tasks": ["benchmarks.tasks:task_a"],
            "solver": "basic_agent",
            "solver_config": {"max_steps": 4, "tools": ["search"]},
        },
        default_task="unused",
    )
    same_values_different_order = InspectRunnerConfig.from_mapping(
        {
            "solver_config": {"tools": ["search"], "max_steps": 4},
            "solver": "basic_agent",
            "tasks": ["benchmarks.tasks:task_a"],
            "model": "model-a",
        },
        default_task="unused",
    )
    variation = InspectRunnerConfig.from_mapping(
        {
            "model": "model-a",
            "tasks": ["benchmarks.tasks:task_a"],
            "solver": "react_agent",
            "solver_config": {"max_steps": 4, "tools": ["search"]},
        },
        default_task="unused",
    )

    first = configuration_provenance(
        baseline, inspect_version="1.2.3", dataset_version="v1"
    )
    second = configuration_provenance(
        same_values_different_order, inspect_version="1.2.3", dataset_version="v1"
    )
    changed = configuration_provenance(
        variation, inspect_version="1.2.3", dataset_version="v1"
    )

    assert first["configuration_fingerprint"] == second["configuration_fingerprint"]
    assert first["configuration_fingerprint"] != changed["configuration_fingerprint"]


def test_inspect_runner_fails_explicitly_without_partial_scores() -> None:
    runner = InspectEvaluationRunner(
        executor=lambda _config: {
            "status": "failed",
            "error": "model endpoint unavailable",
            "score": 1.0,
        }
    )

    with pytest.raises(InspectRunnerError, match="model endpoint unavailable"):
        runner.evaluate(
            _request(
                {
                    "model": "model-a",
                    "solver": "basic_agent",
                    "tasks": ["benchmarks.tasks:task_a"],
                }
            )
        )


def test_inspect_runner_rejects_an_invalid_solver_identifier() -> None:
    config = InspectRunnerConfig.from_mapping(
        {"model": "model-a", "solver": "outside_package:solver"},
        default_task="benchmarks.tasks:task_a",
    )

    with pytest.raises(InspectRunnerError, match="scaffold_failure"):
        _resolve_solver(config)


def test_inspect_installation_can_omit_solver_but_a_resolved_run_cannot() -> None:
    runner = InspectEvaluationRunner(executor=lambda _config: {"status": "success"})

    runner.validate_configuration(
        {"model": "model-a", "tasks": ["benchmarks.tasks:task_a"]}
    )
    with pytest.raises(InspectRunnerError, match="scaffold_failure"):
        InspectRunnerConfig.from_mapping(
            {"model": "model-a", "tasks": ["benchmarks.tasks:task_a"]},
            default_task="unused",
        )


def test_inspect_rejects_known_gpt5_tool_transport_before_dispatch() -> None:
    runner = InspectEvaluationRunner(executor=lambda _config: {"status": "success"})

    with pytest.raises(InspectRunnerError, match="Chat Completions transport"):
        runner.validate_run_configuration(
            {
                "model": "openai/gpt-5.6-luna",
                "solver": "ai_governance.inspect_tasks:controlled_trajectory_solver",
                "tasks": ["ai_governance.inspect_tasks:trajectory_fidelity_smoke"],
                "requires_tools": True,
            }
        )

    with pytest.raises(InspectRunnerError, match="Chat Completions transport"):
        runner.validate_configuration(
            {
                "model": "openai/gpt-5.6-luna",
                "tasks": ["ai_governance.inspect_tasks:trajectory_fidelity_smoke"],
                "requires_tools": True,
            }
        )


def test_inspect_provenance_fingerprint_includes_declared_tool_use() -> None:
    runner = InspectEvaluationRunner(executor=lambda _config: {"status": "success"})
    base = {
        "model": "model-a",
        "solver": "generate",
        "tasks": ["ai_governance.inspect_tasks:scaffold_smoke"],
    }

    without_tools = runner.capture_runner_provenance(base, "smoke-v1")
    with_tools = runner.capture_runner_provenance(
        {**base, "requires_tools": True}, "smoke-v1"
    )

    assert without_tools["requires_tools"] is False
    assert with_tools["requires_tools"] is True
    assert (
        without_tools["configuration_fingerprint"]
        != with_tools["configuration_fingerprint"]
    )


def test_inspect_workload_estimate_uses_task_limit_not_control_plane_dataset() -> None:
    runner = InspectEvaluationRunner(executor=lambda _config: {"status": "success"})

    estimate = runner.estimate_workload(
        {
            "model": "model-a",
            "solver": "generate",
            "tasks": [
                "ai_governance.inspect_tasks:scaffold_smoke",
                "ai_governance.inspect_tasks:trajectory_fidelity_smoke",
            ],
            "task_limit": 2,
        }
    )

    assert estimate.runner_invocation_count == 1
    assert estimate.expected_sample_result_count == 4


def test_packaged_smoke_task_has_ten_exact_samples_and_solver_resolves() -> None:
    from ai_governance.inspect_tasks import (
        planning_instruction_generate,
        scaffold_smoke,
    )

    smoke_task = scaffold_smoke()
    assert len(smoke_task.dataset) == 10
    assert [sample.target for sample in smoke_task.dataset] == [
        "2",
        "7",
        "3",
        "3",
        "12",
        "B",
        "January",
        "7",
        "blue",
        "cold",
    ]
    assert planning_instruction_generate(planning_prompt_version="v1")
    config = InspectRunnerConfig.from_mapping(
        {
            "model": "model-a",
            "tasks": ["ai_governance.inspect_tasks:scaffold_smoke"],
            "solver": "ai_governance.inspect_tasks:planning_instruction_generate",
            "solver_config": {"planning_prompt_version": "v1"},
        },
        default_task="unused",
    )
    assert _resolve_solver(config)


def test_planner_executor_fixture_has_ten_multistep_samples_and_two_model_calls() -> (
    None
):
    from ai_governance.evaluation.scaffold_artifacts import (
        SCAFFOLD_PLAN_SCHEMA_VERSION,
        SCAFFOLD_PLAN_STORE_KEY,
    )
    from ai_governance.inspect_tasks import (
        planner_executor_generate,
        planner_executor_smoke,
    )

    task = planner_executor_smoke()
    assert len(task.dataset) == 10
    assert task.metadata["expected_baseline_model_calls_per_sample"] == 1
    assert task.metadata["expected_planner_model_calls_per_sample"] == 2

    class FakeStore:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        def set(self, key: str, value: object) -> None:
            self.values[key] = value

    state = SimpleNamespace(
        input_text="Solve the sample task.",
        user_prompt=SimpleNamespace(text="Solve the sample task."),
        output=SimpleNamespace(completion=""),
        store=FakeStore(),
        messages=[],
    )
    calls: list[dict[str, object]] = []

    async def model_generate(fake_state: object, **kwargs: object) -> object:
        calls.append(dict(kwargs))
        fake_state.output.completion = (
            '{"steps":["identify values","calculate result"]}'
            if len(calls) == 1
            else "42"
        )
        return fake_state

    result = asyncio.run(planner_executor_generate()(state, model_generate))

    assert result.output.completion == "42"
    assert calls == [{"tool_calls": "none"}, {"tool_calls": "none"}]
    assert "Original task:\nSolve the sample task." in result.messages[-1].text
    assert result.store.values[SCAFFOLD_PLAN_STORE_KEY] == {
        "schema_version": SCAFFOLD_PLAN_SCHEMA_VERSION,
        "content_digest": hashlib.sha256(
            b'{"steps":["identify values","calculate result"]}'
        ).hexdigest(),
        "stage": "planning",
    }


def test_inspect_batch_retains_safe_per_call_usage_and_plan_artifact() -> None:
    runner = InspectEvaluationRunner(
        executor=lambda _config: [
            {
                "samples": [
                    {
                        "id": "planner-sample",
                        "scores": {"exact": {"value": "C"}},
                        "model_usage": {
                            "model-a": {
                                "input_tokens": 10,
                                "output_tokens": 7,
                                "total_tokens": 17,
                            }
                        },
                        "events": [
                            {
                                "event": "model",
                                "output": {
                                    "usage": {
                                        "input_tokens": 4,
                                        "output_tokens": 2,
                                        "total_tokens": 6,
                                    },
                                    "time": 0.2,
                                },
                            },
                            {
                                "event": "model",
                                "output": {
                                    "usage": {
                                        "input_tokens": 6,
                                        "output_tokens": 5,
                                        "total_tokens": 11,
                                    },
                                    "time": 0.3,
                                },
                            },
                        ],
                        "store": {
                            "ai_governance.scaffold.plan": {
                                "schema_version": "planner-executor-plan/v1",
                                "content_digest": "sha256-plan-digest",
                                "stage": "planning",
                            }
                        },
                    }
                ]
            }
        ]
    )

    batch = runner.evaluate_batch(
        _request(
            {
                "model": "model-a",
                "solver": "ai_governance.inspect_tasks:planner_executor_generate",
                "tasks": ["ai_governance.inspect_tasks:planner_executor_smoke"],
            }
        )
    )

    sample = batch.sample_results[0]
    metrics = {metric.metric_name: metric.metric_value for metric in sample.metrics}
    assert metrics["model_call_count"] == 2.0
    assert metrics["total_tokens"] == 17.0
    assert sample.metadata["model_call_usage"] == [
        {
            "call_index": 1,
            "input_tokens": 4.0,
            "output_tokens": 2.0,
            "total_tokens": 6.0,
            "duration_seconds": 0.2,
        },
        {
            "call_index": 2,
            "input_tokens": 6.0,
            "output_tokens": 5.0,
            "total_tokens": 11.0,
            "duration_seconds": 0.3,
        },
    ]
    plan_artifact = next(
        artifact
        for artifact in sample.artifacts
        if artifact.artifact_type == "scaffold_plan"
    )
    assert plan_artifact.metadata["content_retained"] is False


def test_packaged_trajectory_fixture_uses_real_deterministic_tools() -> None:
    from ai_governance.inspect_tasks import (
        controlled_trajectory_solver,
        trajectory_fidelity_smoke,
    )

    task = trajectory_fidelity_smoke()
    assert len(task.dataset) == 4
    assert task.metadata["deterministic_tools"] is True
    assert controlled_trajectory_solver()


def test_inspect_runner_rejects_host_local_task_paths() -> None:
    with pytest.raises(InspectRunnerError, match="task_definition_failure"):
        InspectRunnerConfig.from_mapping(
            {
                "model": "model-a",
                "solver": "generate",
                "tasks": ["path/to/task.py"],
            },
            default_task="benchmarks.tasks:task_a",
        )


def test_inspect_runner_aggregates_a_bounded_task_set() -> None:
    runner = InspectEvaluationRunner(
        executor=lambda _config: [
            {"status": "success", "passed": True, "score": 1.0},
            {"status": "success", "passed": False, "score": 0.0},
        ]
    )

    result = runner.evaluate(
        _request(
            {
                "model": "model-a",
                "solver": "basic_agent",
                "tasks": ["benchmarks.tasks:task_a", "benchmarks.tasks:task_b"],
                "task_limit": 1,
            }
        )
    )

    assert {metric.metric_name: metric.metric_value for metric in result.metrics} == {
        "pass": 0.5,
        "score": 0.5,
        "tool_action_count": 0.0,
    }
    assert result.provider_metadata["task_result_count"] == 2


def test_inspect_runner_normalizes_inspect_sample_logs() -> None:
    runner = InspectEvaluationRunner(
        executor=lambda _config: [
            {
                "samples": [
                    {
                        "scores": {"exact": {"value": "C"}},
                        "model_usage": {
                            "model-a": {
                                "input_tokens": 3,
                                "output_tokens": 2,
                                "total_tokens": 5,
                            }
                        },
                        "events": [
                            {"event": "model", "output": {"time": 0.25}},
                            {"event": "tool"},
                        ],
                    },
                    {
                        "scores": {"exact": {"value": "I"}},
                        "model_usage": {
                            "model-a": {
                                "input_tokens": 5,
                                "output_tokens": 1,
                                "total_tokens": 6,
                            }
                        },
                        "events": [{"event": "model", "output": {"time": 0.75}}],
                    },
                ]
            }
        ]
    )

    result = runner.evaluate(
        _request(
            {
                "model": "model-a",
                "solver": "generate",
                "tasks": ["benchmarks.tasks:task_a"],
            }
        )
    )

    assert {metric.metric_name: metric.metric_value for metric in result.metrics} == {
        "pass": 0.5,
        "score": 0.5,
        "tool_action_count": 0.5,
        "model_call_count": 1.0,
        "input_tokens": 4.0,
        "output_tokens": 1.5,
        "total_tokens": 5.5,
        "wall_clock_duration_seconds": 0.5,
    }
    assert result.provider_metadata["task_result_count"] == 2


def test_inspect_runner_returns_provider_neutral_batch_samples() -> None:
    runner = InspectEvaluationRunner(
        executor=lambda _config: [
            {
                "samples": [
                    {"id": "one", "scores": {"exact": {"value": "C"}}},
                    {"id": "two", "scores": {"exact": {"value": "I"}}},
                ]
            }
        ]
    )

    batch = runner.evaluate_batch(
        _request(
            {
                "model": "model-a",
                "solver": "generate",
                "tasks": ["benchmarks.tasks:task_a"],
            }
        )
    )

    assert [sample.sample_id for sample in batch.sample_results] == ["one", "two"]
    assert [sample.metrics[0].metric_value for sample in batch.sample_results] == [
        1.0,
        0.0,
    ]


def test_inspect_results_remain_tenant_scoped() -> None:
    runner = InspectEvaluationRunner(
        executor=lambda _config: {"status": "success", "passed": True, "score": 1.0}
    )
    registry = EvaluationProviderRegistry()
    registry.register(runner)
    service = EvaluationApiService(registry, InMemoryEvaluationRepository())
    owner = TenantContext("org-a", "project-a", "actor-a", "request-a")
    other = TenantContext("org-b", "project-b", "actor-b", "request-b")

    result = service.submit_evaluation(
        _request(
            {
                "model": "model-a",
                "solver": "basic_agent",
                "tasks": ["benchmarks.tasks:task_a"],
            }
        ).execution,
        "inspect_ai",
        provider_config={
            "model": "model-a",
            "solver": "basic_agent",
            "tasks": ["benchmarks.tasks:task_a"],
        },
        context=owner,
    )

    assert (
        service.get_evaluation(result.evaluation_id, owner).evaluation_id
        == result.evaluation_id
    )
    with pytest.raises(EvaluationNotFoundError):
        service.get_evaluation(result.evaluation_id, other)


def test_controlled_variants_keep_fixed_config_and_vary_scaffold() -> None:
    fixed = {
        "model": "model-a",
        "tasks": ["benchmarks.tasks:task_a"],
        "scorer": "exact",
    }
    baseline = _candidate("basic_agent")
    variant = _candidate("react_agent")

    baseline_config = ExperimentApiService._provider_config_for_candidate(
        object(), baseline, fixed, None
    )
    variant_config = ExperimentApiService._provider_config_for_candidate(
        object(), variant, fixed, None
    )

    assert baseline_config["model"] == variant_config["model"] == "model-a"
    assert (
        baseline_config["tasks"]
        == variant_config["tasks"]
        == ["benchmarks.tasks:task_a"]
    )
    assert baseline_config["scorer"] == variant_config["scorer"] == "exact"
    assert baseline_config["solver"] == "basic_agent"
    assert variant_config["solver"] == "react_agent"


def test_core_domain_has_no_inspect_sdk_import() -> None:
    tree = ast.parse(Path("src/ai_governance/domain/evaluation_result.py").read_text())
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and "inspect_ai" in ast.dump(node)
        for node in ast.walk(tree)
    )


def _request(provider_config: dict[str, object]) -> EvaluationRequest:
    execution = WorkflowExecution(
        workflow_id="workflow-a",
        execution_id="execution-a",
        workflow_name="workflow-task",
        workflow_version="1",
        execution_status="COMPLETED",
        input={"input": "Question"},
        final_state={"answer": "Answer"},
        events=[],
        metadata={"dataset_version": "v1"},
    )
    from ai_governance.services.dataset_builder import EvaluationDatasetBuilder

    return EvaluationRequest(
        execution=execution,
        dataset=EvaluationDatasetBuilder().build(execution),
        provider_config=provider_config,
    )


def _candidate(solver: str) -> ExperimentCandidate:
    return ExperimentCandidate(
        candidate_id=f"candidate-{solver}",
        experiment_id="experiment-a",
        name=solver,
        prompt_id="prompt-a",
        prompt_version="1",
        model_id="model-a",
        model_version="1",
        dataset_id="dataset-a",
        dataset_version="1",
        evaluation_provider="inspect_ai",
        temperature=0.0,
        top_p=1.0,
        max_tokens=100,
        metadata={"evaluation_runner_config": {"solver": solver}},
        created_at=datetime(2026, 9, 6, tzinfo=UTC),
    )
