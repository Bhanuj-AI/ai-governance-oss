from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

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
        executor=lambda config: received.append(config) or {
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


def test_inspect_configuration_fingerprint_is_deterministic_and_changes_for_solver() -> None:
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
                {"model": "model-a", "solver": "basic_agent", "tasks": ["benchmarks.tasks:task_a"]}
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
    from ai_governance.inspect_tasks import plan_then_generate, scaffold_smoke

    smoke_task = scaffold_smoke()
    assert len(smoke_task.dataset) == 10
    assert [sample.target for sample in smoke_task.dataset] == [
        "2", "7", "3", "3", "12", "B", "January", "7", "blue", "cold"
    ]
    assert plan_then_generate(planning_prompt_version="v1")
    config = InspectRunnerConfig.from_mapping(
        {
            "model": "model-a",
            "tasks": ["ai_governance.inspect_tasks:scaffold_smoke"],
            "solver": "ai_governance.inspect_tasks:plan_then_generate",
            "solver_config": {"planning_prompt_version": "v1"},
        },
        default_task="unused",
    )
    assert _resolve_solver(config)


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
            {"model": "model-a", "solver": "generate", "tasks": ["benchmarks.tasks:task_a"]}
        )
    )

    assert {metric.metric_name: metric.metric_value for metric in result.metrics} == {
        "pass": 0.5,
        "score": 0.5,
        "tool_action_count": 0.5,
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
            {"model": "model-a", "solver": "generate", "tasks": ["benchmarks.tasks:task_a"]}
        )
    )

    assert [sample.sample_id for sample in batch.sample_results] == ["one", "two"]
    assert [sample.metrics[0].metric_value for sample in batch.sample_results] == [1.0, 0.0]


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
            _request({"model": "model-a", "solver": "basic_agent", "tasks": ["benchmarks.tasks:task_a"]}).execution,
        "inspect_ai",
        provider_config={"model": "model-a", "solver": "basic_agent", "tasks": ["benchmarks.tasks:task_a"]},
        context=owner,
    )

    assert service.get_evaluation(result.evaluation_id, owner).evaluation_id == result.evaluation_id
    with pytest.raises(EvaluationNotFoundError):
        service.get_evaluation(result.evaluation_id, other)


def test_controlled_variants_keep_fixed_config_and_vary_scaffold() -> None:
    fixed = {"model": "model-a", "tasks": ["benchmarks.tasks:task_a"], "scorer": "exact"}
    baseline = _candidate("basic_agent")
    variant = _candidate("react_agent")

    baseline_config = ExperimentApiService._provider_config_for_candidate(
        object(), baseline, fixed, None
    )
    variant_config = ExperimentApiService._provider_config_for_candidate(
        object(), variant, fixed, None
    )

    assert baseline_config["model"] == variant_config["model"] == "model-a"
    assert baseline_config["tasks"] == variant_config["tasks"] == ["benchmarks.tasks:task_a"]
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
