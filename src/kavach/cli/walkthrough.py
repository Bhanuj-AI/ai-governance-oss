"""A deliberately narrow, public-API-only governed replay walkthrough."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

import yaml

from kavach.mcp.clients.rest_client import RestClientError

if TYPE_CHECKING:
    from kavach.cli.walkthrough_renderers import WalkthroughRenderer


class WalkthroughError(Exception):
    """A public API response did not satisfy the scenario's requirements."""


class WalkthroughClient(Protocol):
    """The small public REST surface the scenario is allowed to orchestrate."""

    def get(self, path: str, *, query: Mapping[str, Any] | None = None) -> Any: ...

    def post(self, path: str, *, body: Mapping[str, Any] | None = None) -> Any: ...


@dataclass(frozen=True)
class WalkthroughLifecycleEvent:
    """A structured, transport-neutral notification about a walkthrough run."""

    name: str
    walkthrough_id: str
    run_id: str
    tenant_id: str
    step_id: str | None = None
    action: str | None = None
    status: str | None = None
    inspect_url: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WalkthroughConfiguration:
    api_url: str
    studio_url: str
    organization_id: str
    project_id: str
    source_execution_id: str | None = None
    submit_replay: bool = False
    continue_after_submission_failure: bool = False
    manifest_path: Path | None = None


@dataclass(frozen=True)
class ScenarioDefinition:
    api_version: str
    scenario_id: str
    title: str
    description: str
    category: str
    world: str
    level_title: str
    prompt: Mapping[str, Any]
    model: Mapping[str, Any]
    dataset_id: str
    steps: tuple[Mapping[str, str], ...]


@dataclass
class WalkthroughStep:
    step_id: str
    action: str
    endpoint: str
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    inspect_url: str | None = None


@dataclass
class WalkthroughManifest:
    api_version: str
    walkthrough_id: str
    run_id: str
    tenant_id: str
    organization_id: str
    project_id: str
    started_at: str
    completed_at: str | None
    outcome: str
    failure: dict[str, Any] | None
    scenario: dict[str, str]
    resources: dict[str, str]
    created_assets: list[str]
    selected_assets: list[str]
    urls: dict[str, str]
    steps: list[WalkthroughStep]
    manifest_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CleanupResult:
    directory: str
    older_than_days: int
    candidates: list[str]
    removed: list[str]


def run_governed_replay(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    *,
    renderer: WalkthroughRenderer | None = None,
) -> WalkthroughManifest:
    """Run the golden path without reaching beneath Kavach's public REST API."""
    scenario = load_governed_replay_scenario()
    if scenario.api_version != "v1":
        raise WalkthroughError(
            f"Walkthrough API version '{scenario.api_version}' is not supported by this CLI."
        )
    run_id = f"walkthrough-{uuid4().hex[:12]}"
    manifest_path = configuration.manifest_path or _default_manifest_path(
        scenario.scenario_id, run_id
    )
    manifest = WalkthroughManifest(
        api_version=scenario.api_version,
        walkthrough_id=scenario.scenario_id,
        run_id=run_id,
        tenant_id=f"{configuration.organization_id}/{configuration.project_id}",
        organization_id=configuration.organization_id,
        project_id=configuration.project_id,
        started_at=_now(),
        completed_at=None,
        outcome="RUNNING",
        failure=None,
        scenario={"title": scenario.title, "description": scenario.description},
        resources={},
        created_assets=[],
        selected_assets=[],
        urls={},
        steps=[],
        manifest_path=str(manifest_path),
    )
    _checkpoint(manifest, manifest_path)
    _emit(
        renderer,
        manifest,
        "walkthrough_started",
        data={
            "title": scenario.title,
            "category": scenario.category,
            "world": scenario.world,
            "level_title": scenario.level_title,
            "step_count": len(scenario.steps),
        },
    )

    try:
        _run_governed_replay_steps(configuration, client, scenario, manifest, renderer)
    except (RestClientError, WalkthroughError) as exc:
        manifest.outcome = "FAILED"
        manifest.completed_at = _now()
        manifest.failure = {"type": type(exc).__name__, "message": str(exc)}
        _write_manifest(manifest, manifest_path)
        completed_step_ids = {step.step_id for step in manifest.steps}
        failed_step = next(
            (
                step
                for step in scenario.steps
                if step.get("id") not in completed_step_ids
            ),
            None,
        )
        _emit(
            renderer,
            manifest,
            "step_failed",
            step_id=failed_step.get("id") if failed_step else None,
            action=failed_step.get("action") if failed_step else None,
            status="FAILED",
            data=manifest.failure,
        )
        _emit(
            renderer,
            manifest,
            "walkthrough_completed",
            status="FAILED",
            data=manifest.failure,
        )
        raise WalkthroughError(f"{exc} Partial run manifest: {manifest_path}") from exc

    manifest.outcome = "COMPLETED"
    manifest.completed_at = _now()
    _write_manifest(manifest, manifest_path)
    _emit(renderer, manifest, "walkthrough_completed", status="COMPLETED")
    return manifest


def run_evaluation_pipeline(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    *,
    renderer: WalkthroughRenderer | None = None,
) -> WalkthroughManifest:
    """Teach evaluation evidence discovery without creating governed state."""
    scenario_id = "evaluation-pipeline"
    run_id = f"walkthrough-{uuid4().hex[:12]}"
    manifest_path = configuration.manifest_path or _default_manifest_path(
        scenario_id, run_id
    )
    manifest = WalkthroughManifest(
        api_version="v1",
        walkthrough_id=scenario_id,
        run_id=run_id,
        tenant_id=f"{configuration.organization_id}/{configuration.project_id}",
        organization_id=configuration.organization_id,
        project_id=configuration.project_id,
        started_at=_now(),
        completed_at=None,
        outcome="RUNNING",
        failure=None,
        scenario={
            "title": "Evaluation Pipeline",
            "description": "Inspect immutable evaluation evidence through public APIs.",
        },
        resources={},
        created_assets=[],
        selected_assets=[],
        urls={},
        steps=[],
        manifest_path=str(manifest_path),
    )
    _checkpoint(manifest, manifest_path)
    _emit(
        renderer,
        manifest,
        "walkthrough_started",
        data={
            "title": "Evaluation Pipeline",
            "category": "evaluation",
            "world": "1-2",
            "level_title": "Measure the Signal",
            "step_count": 3,
        },
    )
    try:
        _emit_step_started(
            renderer, manifest, "select_execution", "Choose evaluated execution"
        )
        source = _select_source_execution(client, configuration.source_execution_id)
        execution_id = _required_string(source, "execution_id", "evaluation source")
        manifest.resources["source_execution_id"] = execution_id
        manifest.selected_assets.append(f"execution:{execution_id}")
        execution_url = _studio_url(configuration, f"/replay-executions/{execution_id}")
        _record_step(
            manifest,
            renderer,
            WalkthroughStep(
                "select_execution",
                "Choose evaluated execution",
                "GET /api/v1/replay-executions/search",
                "COMPLETED",
                _summary(source, "execution_id", "workflow_name", "workflow_version"),
                execution_url,
            ),
        )
        _checkpoint(manifest)
        _emit_step_started(
            renderer,
            manifest,
            "inspect_history",
            "Inspect immutable evaluation history",
        )
        history = _get_evaluation_history(client, execution_id)
        evaluations = _mapping_list(history.get("evaluations"))
        _record_step(
            manifest,
            renderer,
            WalkthroughStep(
                "inspect_history",
                "Inspect immutable evaluation history",
                f"GET /api/v1/evaluations/history/{execution_id}",
                "COMPLETED" if evaluations else "SKIPPED",
                {
                    "execution_id": execution_id,
                    "evaluation_count": len(evaluations),
                    "reason": "No evaluations are available."
                    if not evaluations
                    else "",
                },
                execution_url,
            ),
        )
        _checkpoint(manifest)
        _emit_step_started(
            renderer, manifest, "inspect_metrics", "Read evaluator metrics"
        )
        if not evaluations or not isinstance(evaluations[0].get("evaluation_id"), str):
            _record_step(
                manifest,
                renderer,
                WalkthroughStep(
                    "inspect_metrics",
                    "Read evaluator metrics",
                    "GET /api/v1/evaluations/{evaluation_id}",
                    "SKIPPED",
                    {"reason": "No evaluation record is available."},
                ),
            )
            _checkpoint(manifest)
        else:
            evaluation_id = evaluations[0]["evaluation_id"]
            evaluation = _mapping(client.get(f"/api/v1/evaluations/{evaluation_id}"))
            manifest.resources["evaluation_id"] = evaluation_id
            evaluation_url = _studio_url(configuration, f"/evaluations/{evaluation_id}")
            _record_step(
                manifest,
                renderer,
                WalkthroughStep(
                    "inspect_metrics",
                    "Read evaluator metrics",
                    f"GET /api/v1/evaluations/{evaluation_id}",
                    "COMPLETED",
                    _summary(
                        evaluation,
                        "evaluation_id",
                        "evaluator_type",
                        "evaluator_version",
                        "metrics",
                    ),
                    evaluation_url,
                ),
            )
            _checkpoint(manifest)
    except (RestClientError, WalkthroughError) as exc:
        manifest.outcome = "FAILED"
        manifest.completed_at = _now()
        manifest.failure = {"type": type(exc).__name__, "message": str(exc)}
        _write_manifest(manifest, manifest_path)
        _emit(
            renderer,
            manifest,
            "walkthrough_completed",
            status="FAILED",
            data=manifest.failure,
        )
        raise WalkthroughError(f"{exc} Partial run manifest: {manifest_path}") from exc
    manifest.outcome = "COMPLETED"
    manifest.completed_at = _now()
    _write_manifest(manifest, manifest_path)
    _emit(renderer, manifest, "walkthrough_completed", status="COMPLETED")
    return manifest


def run_policy_gate(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    *,
    renderer: WalkthroughRenderer | None = None,
) -> WalkthroughManifest:
    """Teach policy discovery without changing policy administration state."""
    return _run_read_only_walkthrough(
        configuration,
        client,
        renderer=renderer,
        walkthrough_id="policy-gate",
        title="Policy Gate",
        description="Inspect tenant-scoped policy schema, versions, and rules.",
        category="governance",
        world="1-3",
        level_title="Open the Policy Gate",
        step_count=3,
        runner=_run_policy_gate_steps,
    )


def run_decision_detective(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    *,
    renderer: WalkthroughRenderer | None = None,
) -> WalkthroughManifest:
    """Teach decision evidence discovery without creating a decision."""
    return _run_read_only_walkthrough(
        configuration,
        client,
        renderer=renderer,
        walkthrough_id="decision-detective",
        title="Decision Detective",
        description="Trace decision evidence and deterministic explanations.",
        category="governance",
        world="2-1",
        level_title="Follow the Evidence Trail",
        step_count=3,
        runner=_run_decision_detective_steps,
    )


def run_experiment_arena(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    *,
    renderer: WalkthroughRenderer | None = None,
) -> WalkthroughManifest:
    """Teach experiment evidence discovery without changing experiment state."""
    return _run_read_only_walkthrough(
        configuration,
        client,
        renderer=renderer,
        walkthrough_id="experiment-arena",
        title="Experiment Arena",
        description="Inspect candidates and evidence-backed outcomes.",
        category="experiments",
        world="2-2",
        level_title="Scout the Candidate Field",
        step_count=3,
        runner=_run_experiment_arena_steps,
    )


def _run_experiment_arena_steps(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    manifest: WalkthroughManifest,
    renderer: WalkthroughRenderer | None,
) -> None:
    _emit_step_started(
        renderer, manifest, "select_experiment", "Choose an experiment arena"
    )
    experiments = _mapping_list(client.get("/api/v1/experiments"))
    if not experiments:
        _record_step(
            manifest,
            renderer,
            WalkthroughStep(
                "select_experiment",
                "Choose an experiment arena",
                "GET /api/v1/experiments",
                "SKIPPED",
                {"reason": "No experiment is available in this tenant."},
            ),
        )
        _checkpoint(manifest)
        return
    experiment = next(
        (item for item in experiments if item.get("status") == "COMPLETED"),
        experiments[0],
    )
    experiment_id = _required_string(experiment, "experiment_id", "experiment list")
    manifest.resources["experiment_id"] = experiment_id
    url = _studio_url(configuration, f"/experiments/{experiment_id}")
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "select_experiment",
            "Choose an experiment arena",
            "GET /api/v1/experiments",
            "COMPLETED",
            _summary(experiment, "experiment_id", "name", "status"),
            url,
        ),
    )
    _checkpoint(manifest)
    _emit_step_started(
        renderer, manifest, "inspect_candidates", "Inspect competing candidates"
    )
    candidates = _mapping_list(
        client.get(f"/api/v1/experiments/{experiment_id}/candidates")
    )
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "inspect_candidates",
            "Inspect competing candidates",
            f"GET /api/v1/experiments/{experiment_id}/candidates",
            "COMPLETED" if candidates else "SKIPPED",
            {
                "candidate_count": len(candidates),
                "reason": "No candidates are available." if not candidates else "",
            },
            url,
        ),
    )
    _checkpoint(manifest)
    _emit_step_started(
        renderer, manifest, "inspect_outcome", "Inspect the evidence-backed outcome"
    )
    insights = _mapping(client.get(f"/api/v1/experiments/{experiment_id}/insights"))
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "inspect_outcome",
            "Inspect the evidence-backed outcome",
            f"GET /api/v1/experiments/{experiment_id}/insights",
            "COMPLETED",
            _summary(insights, "status", "summary", "recommendations"),
            url,
        ),
    )
    _checkpoint(manifest)


def _run_decision_detective_steps(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    manifest: WalkthroughManifest,
    renderer: WalkthroughRenderer | None,
) -> None:
    _emit_step_started(
        renderer, manifest, "find_decision", "Find a persisted governance decision"
    )
    decision = _select_decision(client)
    if decision is None:
        _record_step(
            manifest,
            renderer,
            WalkthroughStep(
                "find_decision",
                "Find a persisted governance decision",
                "GET /api/v1/decisions",
                "SKIPPED",
                {"reason": "No decision is available in this tenant."},
            ),
        )
        _checkpoint(manifest)
        return
    decision_id = _required_string(decision, "decision_id", "governance decision")
    manifest.resources["decision_id"] = decision_id
    url = _studio_url(configuration, f"/decisions/{decision_id}")
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "find_decision",
            "Find a persisted governance decision",
            "GET /api/v1/decisions",
            "COMPLETED",
            _summary(decision, "decision_id", "status", "decision_type"),
            url,
        ),
    )
    _checkpoint(manifest)
    _emit_step_started(
        renderer, manifest, "inspect_evidence", "Trace policy and audit evidence"
    )
    detail = _mapping(client.get(f"/api/v1/decisions/{decision_id}/detail"))
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "inspect_evidence",
            "Trace policy and audit evidence",
            f"GET /api/v1/decisions/{decision_id}/detail",
            "COMPLETED",
            {
                "decision_id": decision_id,
                "audit_record_count": len(_mapping_list(detail.get("audit_records"))),
            },
            url,
        ),
    )
    _checkpoint(manifest)
    _emit_step_started(
        renderer, manifest, "read_explanation", "Read the deterministic explanation"
    )
    explanation = _mapping(client.get(f"/api/v1/decisions/{decision_id}/explanation"))
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "read_explanation",
            "Read the deterministic explanation",
            f"GET /api/v1/decisions/{decision_id}/explanation",
            "COMPLETED",
            _summary(explanation, "decision_id", "summary", "reasoning"),
            url,
        ),
    )
    _checkpoint(manifest)


def _run_read_only_walkthrough(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    *,
    renderer: WalkthroughRenderer | None,
    walkthrough_id: str,
    title: str,
    description: str,
    category: str,
    world: str,
    level_title: str,
    step_count: int,
    runner: Any,
) -> WalkthroughManifest:
    run_id = f"walkthrough-{uuid4().hex[:12]}"
    manifest_path = configuration.manifest_path or _default_manifest_path(
        walkthrough_id, run_id
    )
    manifest = WalkthroughManifest(
        "v1",
        walkthrough_id,
        run_id,
        f"{configuration.organization_id}/{configuration.project_id}",
        configuration.organization_id,
        configuration.project_id,
        _now(),
        None,
        "RUNNING",
        None,
        {"title": title, "description": description},
        {},
        [],
        [],
        {},
        [],
        str(manifest_path),
    )
    _checkpoint(manifest, manifest_path)
    _emit(
        renderer,
        manifest,
        "walkthrough_started",
        data={
            "title": title,
            "category": category,
            "world": world,
            "level_title": level_title,
            "step_count": step_count,
        },
    )
    try:
        runner(configuration, client, manifest, renderer)
    except (RestClientError, WalkthroughError) as exc:
        manifest.outcome = "FAILED"
        manifest.completed_at = _now()
        manifest.failure = {"type": type(exc).__name__, "message": str(exc)}
        _write_manifest(manifest, manifest_path)
        _emit(
            renderer,
            manifest,
            "walkthrough_completed",
            status="FAILED",
            data=manifest.failure,
        )
        raise WalkthroughError(f"{exc} Partial run manifest: {manifest_path}") from exc
    manifest.outcome = "COMPLETED"
    manifest.completed_at = _now()
    _write_manifest(manifest, manifest_path)
    _emit(renderer, manifest, "walkthrough_completed", status="COMPLETED")
    return manifest


def _run_policy_gate_steps(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    manifest: WalkthroughManifest,
    renderer: WalkthroughRenderer | None,
) -> None:
    _emit_step_started(
        renderer, manifest, "inspect_schema", "Inspect policy authoring schema"
    )
    schema = _mapping(client.get("/api/v1/policy-schema"))
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "inspect_schema",
            "Inspect policy authoring schema",
            "GET /api/v1/policy-schema",
            "COMPLETED",
            {"target_type_count": len(_mapping_list(schema.get("target_types")))},
        ),
    )
    _checkpoint(manifest)
    _emit_step_started(renderer, manifest, "select_policy", "Find a tenant policy gate")
    policies = _mapping_list(client.get("/api/v1/policies", query={"limit": 1}))
    if not policies:
        _record_step(
            manifest,
            renderer,
            WalkthroughStep(
                "select_policy",
                "Find a tenant policy gate",
                "GET /api/v1/policies",
                "SKIPPED",
                {"reason": "No policy is available in this tenant."},
            ),
        )
        _checkpoint(manifest)
        return
    policy = policies[0]
    policy_id = _required_string(policy, "policy_id", "policy list")
    manifest.resources["policy_id"] = policy_id
    manifest.selected_assets.append(f"policy:{policy_id}")
    url = _studio_url(configuration, f"/policies/{policy_id}")
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "select_policy",
            "Find a tenant policy gate",
            "GET /api/v1/policies",
            "COMPLETED",
            _summary(policy, "policy_id", "name", "status", "category"),
            url,
        ),
    )
    _checkpoint(manifest)
    _emit_step_started(
        renderer, manifest, "inspect_rules", "Inspect active rules and versions"
    )
    detail = _mapping(client.get(f"/api/v1/policies/{policy_id}"))
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            "inspect_rules",
            "Inspect active rules and versions",
            f"GET /api/v1/policies/{policy_id}",
            "COMPLETED",
            _summary(detail, "policy_id", "name", "active_version", "versions"),
            url,
        ),
    )
    _checkpoint(manifest)


def _run_governed_replay_steps(
    configuration: WalkthroughConfiguration,
    client: WalkthroughClient,
    scenario: ScenarioDefinition,
    manifest: WalkthroughManifest,
    renderer: WalkthroughRenderer | None,
) -> None:
    """Perform the versioned scenario and checkpoint every durable outcome."""
    _emit_step_started(renderer, manifest, "observe_prompt", "Observe prompt identity")
    prompt = _observe_prompt(client, scenario)
    prompt_id = _required_string(prompt, "prompt_id", "prompt observation")
    manifest.resources["prompt_id"] = prompt_id
    manifest.created_assets.append(f"prompt:{prompt_id}")
    prompt_url = _studio_url(configuration, f"/assets/prompts/{prompt_id}")
    manifest.urls["prompt"] = prompt_url
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            step_id="observe_prompt",
            action="Observe prompt identity",
            endpoint="POST /api/v1/prompts/observations",
            status="COMPLETED",
            result=_summary(prompt, "prompt_id", "name", "version", "provenance"),
            inspect_url=prompt_url,
        ),
    )
    _checkpoint(manifest)

    _emit_step_started(
        renderer, manifest, "observe_model", "Observe model runtime configuration"
    )
    model = _observe_model(client, scenario)
    model_id = _required_string(model, "model_id", "model observation")
    manifest.resources["model_id"] = model_id
    manifest.created_assets.append(f"model:{model_id}")
    model_url = _studio_url(configuration, f"/assets/models/{model_id}")
    manifest.urls["model"] = model_url
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            step_id="observe_model",
            action="Observe model runtime configuration",
            endpoint="POST /api/v1/models/observations",
            status="COMPLETED",
            result=_summary(
                model, "model_id", "provider", "model_name", "version", "provenance"
            ),
            inspect_url=model_url,
        ),
    )
    _checkpoint(manifest)

    _emit_step_started(
        renderer, manifest, "select_dataset", "Select immutable evaluation dataset"
    )
    dataset = _select_dataset(client, scenario.dataset_id)
    dataset_id = _required_string(dataset, "dataset_id", "dataset selection")
    manifest.resources["dataset_id"] = dataset_id
    manifest.selected_assets.append(f"dataset:{dataset_id}")
    dataset_url = _studio_url(configuration, f"/assets/datasets/{dataset_id}")
    manifest.urls["dataset"] = dataset_url
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            step_id="select_dataset",
            action="Select immutable evaluation dataset",
            endpoint="GET /api/v1/datasets",
            status="COMPLETED",
            result=_summary(
                dataset, "dataset_id", "name", "version", "checksum", "record_count"
            ),
            inspect_url=dataset_url,
        ),
    )
    _checkpoint(manifest)

    _emit_step_started(
        renderer, manifest, "select_execution", "Select replayable workflow execution"
    )
    source = _select_source_execution(client, configuration.source_execution_id)
    source_execution_id = _required_string(source, "execution_id", "source execution")
    manifest.resources["source_execution_id"] = source_execution_id
    manifest.selected_assets.append(f"execution:{source_execution_id}")
    execution_url = _studio_url(
        configuration, f"/replay-executions/{source_execution_id}"
    )
    manifest.urls["source_execution"] = execution_url
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            step_id="select_execution",
            action="Select replayable workflow execution",
            endpoint="GET /api/v1/replay-executions/search",
            status="COMPLETED",
            result=_summary(
                source,
                "execution_id",
                "workflow_name",
                "workflow_version",
                "replayable",
            ),
            inspect_url=execution_url,
        ),
    )
    _checkpoint(manifest)

    _emit_step_started(
        renderer,
        manifest,
        "inspect_baseline_evaluation",
        "Inspect baseline evaluation evidence",
    )
    history = _get_evaluation_history(client, source_execution_id)
    evaluations = _mapping_list(history.get("evaluations"))
    evaluation_count = len(evaluations)
    if evaluations and isinstance(evaluations[0].get("evaluation_id"), str):
        manifest.resources["baseline_evaluation_id"] = evaluations[0]["evaluation_id"]
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            step_id="inspect_baseline_evaluation",
            action="Inspect baseline evaluation evidence",
            endpoint=f"GET /api/v1/evaluations/history/{source_execution_id}",
            status="COMPLETED" if evaluation_count else "PENDING",
            result={
                "execution_id": source_execution_id,
                "evaluation_count": evaluation_count,
            },
            inspect_url=execution_url,
        ),
    )
    _checkpoint(manifest)

    _emit_step_started(
        renderer, manifest, "inspect_decision", "Inspect governance decision evidence"
    )
    decision = _select_decision(client)
    if decision is None:
        _record_step(
            manifest,
            renderer,
            WalkthroughStep(
                step_id="inspect_decision",
                action="Inspect governance decision evidence",
                endpoint="GET /api/v1/decisions",
                status="SKIPPED",
                result={
                    "reason": "No persisted governance decision is available in this tenant."
                },
            ),
        )
    else:
        decision_id = _required_string(decision, "decision_id", "governance decision")
        detail = _get_decision_detail(client, decision_id)
        manifest.resources["decision_id"] = decision_id
        manifest.selected_assets.append(f"decision:{decision_id}")
        decision_url = _studio_url(configuration, f"/decisions/{decision_id}")
        manifest.urls["decision"] = decision_url
        _record_step(
            manifest,
            renderer,
            WalkthroughStep(
                step_id="inspect_decision",
                action="Inspect governance decision evidence",
                endpoint=f"GET /api/v1/decisions/{decision_id}/detail",
                status="COMPLETED",
                result={
                    "decision_id": decision_id,
                    "status": _nested_string(detail, "decision", "status"),
                    "audit_record_count": len(
                        _mapping_list(detail.get("audit_records"))
                    ),
                },
                inspect_url=decision_url,
            ),
        )
    _checkpoint(manifest)

    _emit_step_started(
        renderer,
        manifest,
        "create_replay",
        "Prepare governed replay from immutable source evidence",
    )
    replay = _create_replay(client, scenario.scenario_id, source_execution_id)
    replay_id = _required_string(replay, "replay_id", "replay creation")
    manifest.resources["replay_id"] = replay_id
    manifest.created_assets.append(f"replay:{replay_id}")
    replay_url = _studio_url(configuration, f"/replays/{replay_id}")
    manifest.urls["replay"] = replay_url
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            step_id="create_replay",
            action="Prepare governed replay from immutable source evidence",
            endpoint="POST /api/v1/replays",
            status="COMPLETED",
            result=_summary(
                replay, "replay_id", "source_execution_id", "status", "mode"
            ),
            inspect_url=replay_url,
        ),
    )
    _checkpoint(manifest)

    _emit_step_started(renderer, manifest, "submit_replay", "Queue replay execution")
    if configuration.submit_replay:
        replay_status = str(replay.get("status", ""))
        if replay_status in {"COMPLETED", "FAILED", "CANCELLED", "ARCHIVED"}:
            _record_step(
                manifest,
                renderer,
                WalkthroughStep(
                    step_id="submit_replay",
                    action="Queue replay execution",
                    endpoint=f"POST /api/v1/replays/{replay_id}/submit",
                    status="SKIPPED",
                    result={
                        "reason": (
                            f"Replay '{replay_id}' is already {replay_status}; "
                            "the deterministic checkpoint was reused and was not submitted again."
                        ),
                        "replay_status": replay_status,
                    },
                    inspect_url=replay_url,
                ),
            )
            _checkpoint(manifest)
        else:
            try:
                submitted = _submit_replay(client, replay_id)
            except RestClientError as exc:
                if not configuration.continue_after_submission_failure:
                    raise
                _record_step(
                    manifest,
                    renderer,
                    WalkthroughStep(
                        step_id="submit_replay",
                        action="Queue replay execution",
                        endpoint=f"POST /api/v1/replays/{replay_id}/submit",
                        status="FAILED",
                        result={
                            "reason": _rest_error_message(exc),
                            "http_status": exc.status_code,
                        },
                        inspect_url=replay_url,
                    ),
                )
                _checkpoint(manifest)
            else:
                if isinstance(submitted.get("job_id"), str):
                    manifest.resources["replay_job_id"] = submitted["job_id"]
                _record_step(
                    manifest,
                    renderer,
                    WalkthroughStep(
                        step_id="submit_replay",
                        action="Queue replay execution",
                        endpoint=f"POST /api/v1/replays/{replay_id}/submit",
                        status="QUEUED",
                        result={
                            "replay_id": replay_id,
                            "job_id": submitted.get("job_id"),
                            "job_status": submitted.get("job_status"),
                        },
                        inspect_url=replay_url,
                    ),
                )
    else:
        _record_step(
            manifest,
            renderer,
            WalkthroughStep(
                step_id="submit_replay",
                action="Queue replay execution",
                endpoint=f"POST /api/v1/replays/{replay_id}/submit",
                status="NOT_REQUESTED",
                result={"reason": "Pass --submit-replay to queue the prepared replay."},
                inspect_url=replay_url,
            ),
        )
    _checkpoint(manifest)

    graph_url = _studio_url(
        configuration, f"/graph?entityType=PromptVersion&entityId={prompt_id}&depth=3"
    )
    manifest.urls["lineage"] = graph_url
    _emit_step_started(
        renderer, manifest, "inspect_lineage", "Inspect ontology projection"
    )
    lineage = _try_get_lineage(client, prompt_id)
    _record_step(
        manifest,
        renderer,
        WalkthroughStep(
            step_id="inspect_lineage",
            action="Inspect ontology projection",
            endpoint=f"GET /api/v1/ontology/entities/PromptVersion/{prompt_id}/neighbourhood",
            status=lineage["status"],
            result=lineage["result"],
            inspect_url=graph_url,
        ),
    )
    _checkpoint(manifest)


def _emit_step_started(
    renderer: WalkthroughRenderer | None,
    manifest: WalkthroughManifest,
    step_id: str,
    action: str,
) -> None:
    _emit(renderer, manifest, "step_started", step_id=step_id, action=action)


def _record_step(
    manifest: WalkthroughManifest,
    renderer: WalkthroughRenderer | None,
    step: WalkthroughStep,
) -> None:
    """Record durable state, then expose the same state to presentation adapters."""
    manifest.steps.append(step)
    event_name = (
        "step_skipped"
        if step.status == "SKIPPED"
        else "step_failed"
        if step.status == "FAILED"
        else "step_completed"
    )
    _emit(
        renderer,
        manifest,
        event_name,
        step_id=step.step_id,
        action=step.action,
        status=step.status,
        inspect_url=step.inspect_url,
        data={"result": step.result, "endpoint": step.endpoint},
    )


def _emit(
    renderer: WalkthroughRenderer | None,
    manifest: WalkthroughManifest,
    name: str,
    *,
    step_id: str | None = None,
    action: str | None = None,
    status: str | None = None,
    inspect_url: str | None = None,
    data: Mapping[str, Any] | None = None,
) -> None:
    if renderer is None:
        return
    renderer.emit(
        WalkthroughLifecycleEvent(
            name=name,
            walkthrough_id=manifest.walkthrough_id,
            run_id=manifest.run_id,
            tenant_id=manifest.tenant_id,
            step_id=step_id,
            action=action,
            status=status,
            inspect_url=inspect_url,
            data=data or {},
        )
    )


def load_governed_replay_scenario() -> ScenarioDefinition:
    """Load the version-controlled scenario rather than embedding its content in code."""
    path = _repository_root() / "examples" / "governed-replay" / "scenario.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WalkthroughError(f"Cannot read walkthrough scenario at {path}.") from exc
    if not isinstance(document, dict):
        raise WalkthroughError("Walkthrough scenario must be a YAML mapping.")
    try:
        prompt = _mapping(document["assets"]["prompt"])
        model = _mapping(document["assets"]["model"])
        presentation = _mapping(document.get("presentation", {}))
        dataset_id = str(document["assets"]["dataset_id"])
        steps = tuple(_mapping(step) for step in document["steps"])
        return ScenarioDefinition(
            api_version=str(document["api_version"]),
            scenario_id=str(document["id"]),
            title=str(document["title"]),
            description=str(document["description"]),
            category=str(presentation.get("category", "general")),
            world=str(presentation.get("world", "1-1")),
            level_title=str(presentation.get("level_title", "Get Started")),
            prompt=prompt,
            model=model,
            dataset_id=dataset_id,
            steps=steps,
        )
    except (KeyError, TypeError) as exc:
        raise WalkthroughError(
            "Walkthrough scenario is missing a required field."
        ) from exc


def format_walkthrough(manifest: WalkthroughManifest, *, output_json: bool) -> str:
    """Render either script-friendly JSON or concise operator guidance."""
    if output_json:
        return json.dumps(manifest.to_dict(), indent=2, sort_keys=True, default=str)
    lines = [
        f"{manifest.scenario['title']} {manifest.outcome.lower()}",
        f"Run: {manifest.run_id}",
        f"Tenant: {manifest.tenant_id}",
        "",
    ]
    for step in manifest.steps:
        lines.append(f"{step.status:<13} {step.action}")
        if step.inspect_url:
            lines.append(f"  Inspect: {step.inspect_url}")
    lines.extend(("", f"Manifest: {manifest.manifest_path}"))
    return "\n".join(lines)


def _observe_prompt(
    client: WalkthroughClient, scenario: ScenarioDefinition
) -> Mapping[str, Any]:
    prompt = dict(scenario.prompt)
    artifact = (
        _repository_root() / "examples" / "governed-replay" / prompt.pop("artifact")
    )
    try:
        template = artifact.read_text(encoding="utf-8")
    except OSError as exc:
        raise WalkthroughError(f"Cannot read prompt artifact at {artifact}.") from exc
    prompt["template"] = template
    prompt["content_hash"] = f"sha256:{sha256(template.encode()).hexdigest()}"
    return _mapping(client.post("/api/v1/prompts/observations", body=prompt))


def _observe_model(
    client: WalkthroughClient, scenario: ScenarioDefinition
) -> Mapping[str, Any]:
    return _mapping(client.post("/api/v1/models/observations", body=scenario.model))


def _select_dataset(client: WalkthroughClient, dataset_id: str) -> Mapping[str, Any]:
    datasets = _mapping_list(client.get("/api/v1/datasets"))
    for dataset in datasets:
        if dataset.get("dataset_id") == dataset_id:
            return dataset
    raise WalkthroughError(
        f"The walkthrough requires dataset '{dataset_id}'. Start the local stack to seed it."
    )


def _select_source_execution(
    client: WalkthroughClient, source_execution_id: str | None
) -> Mapping[str, Any]:
    if source_execution_id:
        source = _mapping(
            client.get(f"/api/v1/replay-executions/{source_execution_id}")
        )
        if not source.get("replayable"):
            raise WalkthroughError(
                f"Execution '{source_execution_id}' is not replayable."
            )
        return source
    page = _mapping(
        client.get(
            "/api/v1/replay-executions/search",
            query={"replayable_only": True, "limit": 1},
        )
    )
    items = _mapping_list(page.get("items"))
    if not items:
        raise WalkthroughError(
            "No replayable workflow execution is available in this tenant."
        )
    return items[0]


def _get_evaluation_history(
    client: WalkthroughClient, execution_id: str
) -> Mapping[str, Any]:
    return _mapping(client.get(f"/api/v1/evaluations/history/{execution_id}"))


def _select_decision(client: WalkthroughClient) -> Mapping[str, Any] | None:
    page = _mapping(client.get("/api/v1/decisions", query={"limit": 1}))
    decisions = _mapping_list(page.get("decisions"))
    return decisions[0] if decisions else None


def _get_decision_detail(
    client: WalkthroughClient, decision_id: str
) -> Mapping[str, Any]:
    return _mapping(client.get(f"/api/v1/decisions/{decision_id}/detail"))


def _create_replay(
    client: WalkthroughClient, scenario_id: str, source_execution_id: str
) -> Mapping[str, Any]:
    return _mapping(
        client.post(
            "/api/v1/replays",
            body={
                "source_execution_id": source_execution_id,
                "mode": "FULL",
                "configuration_source": "ORIGINAL",
                "idempotency_key": f"walkthrough:{scenario_id}:{source_execution_id}",
                "reason": "Guided governed-replay walkthrough",
                "metadata": {"walkthrough_id": scenario_id},
            },
        )
    )


def _submit_replay(client: WalkthroughClient, replay_id: str) -> Mapping[str, Any]:
    return _mapping(
        client.post(
            f"/api/v1/replays/{replay_id}/submit",
            body={"reason": "Guided governed-replay walkthrough"},
        )
    )


def _try_get_lineage(client: WalkthroughClient, prompt_id: str) -> dict[str, Any]:
    try:
        graph = _mapping(
            client.get(
                f"/api/v1/ontology/entities/PromptVersion/{prompt_id}/neighbourhood",
                query={"depth": 3},
            )
        )
    except RestClientError as exc:
        return {
            "status": "PENDING_PROJECTION",
            "result": {
                "reason": "The ontology projection is not available yet.",
                "http_status": exc.status_code,
            },
        }
    return {
        "status": "COMPLETED",
        "result": {
            "node_count": len(_mapping_list(graph.get("nodes"))),
            "relationship_count": len(_mapping_list(graph.get("relationships"))),
        },
    }


def _rest_error_message(error: RestClientError) -> str:
    """Expose only the public API error message in an interactive manifest."""
    payload = error.payload
    if isinstance(payload, Mapping):
        nested = payload.get("error")
        if isinstance(nested, Mapping) and isinstance(nested.get("message"), str):
            return nested["message"]
        if isinstance(payload.get("detail"), str):
            return payload["detail"]
    return f"Replay submission was rejected with HTTP {error.status_code}."


def _default_manifest_path(scenario_id: str, run_id: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return (
        Path.cwd()
        / ".kavach"
        / "walkthroughs"
        / f"{scenario_id}-{timestamp}-{run_id}.json"
    )


def cleanup_walkthrough_manifests(
    *, root: Path | None = None, older_than_days: int = 7, apply: bool = False
) -> CleanupResult:
    """Preview or remove only aged local walkthrough manifests.

    This never calls Kavach APIs and never removes governed assets. Requiring
    ``apply`` makes deletion of local diagnostic history explicit.
    """
    if older_than_days < 0:
        raise WalkthroughError("Manifest retention days cannot be negative.")
    directory = (root or Path.cwd()) / ".kavach" / "walkthroughs"
    if not directory.exists():
        return CleanupResult(str(directory), older_than_days, [], [])

    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    candidates = [
        path
        for path in directory.glob("*.json")
        if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff
    ]
    removed: list[str] = []
    if apply:
        for path in candidates:
            path.unlink()
            removed.append(str(path))
    return CleanupResult(
        directory=str(directory),
        older_than_days=older_than_days,
        candidates=[str(path) for path in candidates],
        removed=removed,
    )


def format_cleanup(result: CleanupResult, *, output_json: bool) -> str:
    """Render a safe cleanup preview or the exact files that were removed."""
    if output_json:
        return json.dumps(asdict(result), indent=2, sort_keys=True)
    if result.removed:
        return "\n".join(("Removed walkthrough manifests:", *result.removed))
    if result.candidates:
        return "\n".join(
            (
                "Walkthrough manifests eligible for removal (rerun with --apply):",
                *result.candidates,
            )
        )
    return f"No walkthrough manifests older than {result.older_than_days} days."


def _checkpoint(manifest: WalkthroughManifest, path: Path | None = None) -> None:
    """Persist the current state so an interrupted run remains debuggable."""
    _write_manifest(manifest, path or Path(manifest.manifest_path))


def _write_manifest(manifest: WalkthroughManifest, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise WalkthroughError(f"Cannot write run manifest to {path}.") from exc


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _studio_url(configuration: WalkthroughConfiguration, path: str) -> str:
    return f"{configuration.studio_url.rstrip('/')}{path}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WalkthroughError("The public API returned an unexpected response shape.")
    return value


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        return []
    return list(value)


def _required_string(value: Mapping[str, Any], key: str, subject: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate:
        raise WalkthroughError(f"The {subject} response did not include '{key}'.")
    return candidate


def _nested_string(value: Mapping[str, Any], key: str, nested_key: str) -> str | None:
    nested = value.get(key)
    return nested.get(nested_key) if isinstance(nested, Mapping) else None


def _summary(value: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value.get(key) for key in keys if key in value}
