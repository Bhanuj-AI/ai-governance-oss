from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from ai_governance.cli.walkthrough import (
    WalkthroughConfiguration,
    WalkthroughError,
    WalkthroughLifecycleEvent,
    cleanup_walkthrough_manifests,
    format_walkthrough,
    load_governed_replay_scenario,
    run_decision_detective,
    run_evaluation_pipeline,
    run_experiment_arena,
    run_governed_replay,
    run_policy_gate,
)
from ai_governance.cli.main import _parser, _renderer_for
from ai_governance.cli.walkthrough_renderers import JsonRenderer, PlainRenderer, RichRenderer
from ai_governance.mcp.clients import RestClient, RestClientError


def test_walkthrough_requires_an_explicit_bearer_token_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_TOKEN", "stale-shell-token")

    default_arguments = _parser().parse_args(["walkthrough", "governed-replay"])
    explicit_arguments = _parser().parse_args(
        ["walkthrough", "governed-replay", "--token", "caller-token"]
    )

    assert default_arguments.token is None
    assert explicit_arguments.token == "caller-token"


def test_walkthrough_arguments_are_scoped_to_the_selected_scenario() -> None:
    parser = _parser()

    cleanup = parser.parse_args(
        ["walkthrough", "cleanup", "--older-than-days", "14", "--output-json"]
    )
    replay = parser.parse_args(
        [
            "walkthrough",
            "governed-replay",
            "--api-url",
            "http://api.test",
            "--submit-replay",
        ]
    )

    assert cleanup.walkthrough == "cleanup"
    assert cleanup.older_than_days == 14
    assert cleanup.output_json is True
    assert replay.walkthrough == "governed-replay"
    assert replay.api_url == "http://api.test"
    assert replay.submit_replay is True

    with pytest.raises(SystemExit):
        parser.parse_args(["walkthrough", "cleanup", "--api-url", "http://api.test"])


def test_walkthrough_selects_additive_renderers_without_changing_json_mode() -> None:
    parser = _parser()

    plain = parser.parse_args(["walkthrough", "governed-replay"])
    interactive = parser.parse_args(
        ["walkthrough", "governed-replay", "--interactive", "--no-color"]
    )
    themed = parser.parse_args(["walkthrough", "governed-replay", "--theme", "retro"])
    output_json = parser.parse_args(["walkthrough", "governed-replay", "--json"])

    assert isinstance(_renderer_for(plain), PlainRenderer)
    assert isinstance(_renderer_for(interactive), RichRenderer)
    assert isinstance(_renderer_for(themed), RichRenderer)
    assert isinstance(_renderer_for(output_json), JsonRenderer)


def test_read_only_walkthroughs_define_shared_optional_arguments() -> None:
    parser = _parser()

    for walkthrough in ("policy-gate", "decision-detective", "experiment-arena"):
        arguments = parser.parse_args(["walkthrough", walkthrough, "--interactive"])

        assert arguments.source_execution_id is None
        assert arguments.submit_replay is False
        assert arguments.interactive is True


def test_read_only_walkthroughs_use_only_public_get_endpoints(tmp_path: Path) -> None:
    transport = _read_only_walkthrough_transport()
    client = RestClient("http://api.test", transport=transport)
    configuration = _configuration(tmp_path)

    manifests = [
        run_evaluation_pipeline(configuration, client),
        run_policy_gate(configuration, client),
        run_decision_detective(configuration, client),
        run_experiment_arena(configuration, client),
    ]

    assert [manifest.outcome for manifest in manifests] == ["COMPLETED"] * 4
    assert all(method == "GET" for method, _ in transport.calls)
    assert "/api/v1/experiments/experiment-1/insights" in {
        path for _, path in transport.calls
    }
    assert "/api/v1/experiments/experiment-1/leaderboard" not in {
        path for _, path in transport.calls
    }


def test_governed_replay_walkthrough_uses_only_public_api_and_writes_manifest(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []

    def transport(method, path, query, body):
        calls.append(
            (method, path, dict(query) if query else None, dict(body) if body else None)
        )
        if path == "/api/v1/prompts/observations":
            assert body is not None
            assert body["content_hash"].startswith("sha256:")
            return {
                "prompt_id": "prompt-walkthrough-v1",
                "name": body["name"],
                "version": body["version"],
                "provenance": "OBSERVED",
            }
        if path == "/api/v1/models/observations":
            return {
                "model_id": "model-walkthrough-v1",
                "provider": "mock",
                "model_name": "walkthrough-general",
                "version": "2026.07",
                "provenance": "OBSERVED",
            }
        if path == "/api/v1/datasets":
            return [
                {
                    "dataset_id": "demo-dataset-evaluation",
                    "name": "Demo Evaluation Set",
                    "version": "v1.0",
                    "checksum": "checksum",
                    "record_count": 120,
                }
            ]
        if path == "/api/v1/replay-executions/search":
            return {
                "items": [
                    {
                        "execution_id": "demo-source-execution-01",
                        "workflow_name": "Customer support resolution",
                        "workflow_version": "2026.03",
                        "replayable": True,
                    }
                ]
            }
        if path == "/api/v1/evaluations/history/demo-source-execution-01":
            return {"evaluations": [{"evaluation_id": "baseline-1"}]}
        if path == "/api/v1/decisions":
            return {"decisions": [{"decision_id": "decision-1"}]}
        if path == "/api/v1/decisions/decision-1/detail":
            return {
                "decision": {"status": "APPROVED"},
                "audit_records": [{"audit_id": "audit-1"}],
            }
        if path == "/api/v1/replays":
            assert body is not None
            assert (
                body["idempotency_key"]
                == "walkthrough:governed-replay:demo-source-execution-01"
            )
            return {
                "replay_id": "replay-1",
                "source_execution_id": body["source_execution_id"],
                "status": "READY",
                "mode": "FULL",
            }
        if path.endswith("/neighbourhood"):
            return {"nodes": [{"id": "prompt-walkthrough-v1"}], "relationships": []}
        raise AssertionError(f"Unexpected public API call: {method} {path}")

    manifest_path = tmp_path / "governed-replay.json"
    manifest = run_governed_replay(
        WalkthroughConfiguration(
            api_url="http://api.test",
            studio_url="http://studio.test",
            organization_id="org_test",
            project_id="project_test",
            manifest_path=manifest_path,
        ),
        RestClient("http://api.test", transport=transport),
    )

    assert manifest.created_assets == [
        "prompt:prompt-walkthrough-v1",
        "model:model-walkthrough-v1",
        "replay:replay-1",
    ]
    assert manifest.selected_assets == [
        "dataset:demo-dataset-evaluation",
        "execution:demo-source-execution-01",
        "decision:decision-1",
    ]
    assert manifest.urls["replay"] == "http://studio.test/replays/replay-1"
    assert manifest.resources == {
        "prompt_id": "prompt-walkthrough-v1",
        "model_id": "model-walkthrough-v1",
        "dataset_id": "demo-dataset-evaluation",
        "source_execution_id": "demo-source-execution-01",
        "baseline_evaluation_id": "baseline-1",
        "decision_id": "decision-1",
        "replay_id": "replay-1",
    }
    assert manifest.outcome == "COMPLETED"
    assert [call[1] for call in calls] == [
        "/api/v1/prompts/observations",
        "/api/v1/models/observations",
        "/api/v1/datasets",
        "/api/v1/replay-executions/search",
        "/api/v1/evaluations/history/demo-source-execution-01",
        "/api/v1/decisions",
        "/api/v1/decisions/decision-1/detail",
        "/api/v1/replays",
        "/api/v1/ontology/entities/PromptVersion/prompt-walkthrough-v1/neighbourhood",
    ]
    assert json.loads(manifest_path.read_text()) == manifest.to_dict()
    assert "Manifest:" in format_walkthrough(manifest, output_json=False)


def test_governed_replay_records_pending_ontology_projection(tmp_path: Path) -> None:
    def transport(method, path, query, body):
        if path == "/api/v1/prompts/observations":
            return {"prompt_id": "prompt-1", "name": "prompt", "version": "v1"}
        if path == "/api/v1/models/observations":
            return {"model_id": "model-1"}
        if path == "/api/v1/datasets":
            return [{"dataset_id": "demo-dataset-evaluation"}]
        if path == "/api/v1/replay-executions/search":
            return {"items": [{"execution_id": "execution-1", "replayable": True}]}
        if path == "/api/v1/evaluations/history/execution-1":
            return {"evaluations": []}
        if path == "/api/v1/decisions":
            return {"decisions": []}
        if path == "/api/v1/replays":
            return {
                "replay_id": "replay-1",
                "source_execution_id": "execution-1",
                "status": "READY",
                "mode": "FULL",
            }
        if path.endswith("/neighbourhood"):
            raise RestClientError(status_code=404)
        raise AssertionError(path)

    manifest = run_governed_replay(
        WalkthroughConfiguration(
            api_url="http://api.test",
            studio_url="http://studio.test",
            organization_id="org_test",
            project_id="project_test",
            manifest_path=tmp_path / "manifest.json",
        ),
        RestClient("http://api.test", transport=transport),
    )

    lineage = next(step for step in manifest.steps if step.step_id == "inspect_lineage")
    assert lineage.status == "PENDING_PROJECTION"
    assert lineage.result["http_status"] == 404


def test_governed_replay_scenario_is_versioned_and_declarative() -> None:
    scenario = load_governed_replay_scenario()

    assert scenario.api_version == "v1"
    assert scenario.scenario_id == "governed-replay"
    assert scenario.dataset_id == "demo-dataset-evaluation"
    assert scenario.world == "1-1"
    assert scenario.level_title == "Capture the Evidence"
    assert [step["action"] for step in scenario.steps] == [
        "prompt.observe",
        "model.observe",
        "dataset.select_existing",
        "replay_execution.select",
        "evaluation.history",
        "decision.inspect",
        "replay.create",
        "lineage.get",
    ]


def test_repeated_walkthrough_reuses_explicit_ids_without_duplicate_state(
    tmp_path: Path,
) -> None:
    transport = _stateful_transport()
    configuration = _configuration(tmp_path)

    first = run_governed_replay(
        configuration, RestClient("http://api.test", transport=transport)
    )
    second = run_governed_replay(
        WalkthroughConfiguration(
            **{**configuration.__dict__, "manifest_path": tmp_path / "second.json"}
        ),
        RestClient("http://api.test", transport=transport),
    )

    assert first.resources == second.resources
    assert first.created_assets == second.created_assets
    assert transport.created_prompt_count == 1
    assert transport.created_model_count == 1
    assert transport.created_replay_count == 1


def test_partial_failure_writes_checkpoint_and_a_restart_completes(
    tmp_path: Path,
) -> None:
    transport = _stateful_transport(fail_dataset_once=True)
    failed_manifest = tmp_path / "failed.json"
    configuration = _configuration(tmp_path, manifest_path=failed_manifest)

    with pytest.raises(WalkthroughError, match="Partial run manifest"):
        run_governed_replay(
            configuration, RestClient("http://api.test", transport=transport)
        )

    partial = json.loads(failed_manifest.read_text())
    assert partial["outcome"] == "FAILED"
    assert partial["resources"] == {
        "prompt_id": "prompt-walkthrough-v1",
        "model_id": "model-walkthrough-v1",
    }

    restarted = run_governed_replay(
        WalkthroughConfiguration(
            **{**configuration.__dict__, "manifest_path": tmp_path / "restart.json"}
        ),
        RestClient("http://api.test", transport=transport),
    )

    assert restarted.outcome == "COMPLETED"
    assert restarted.resources["replay_id"] == "replay-1"
    assert transport.created_prompt_count == 1
    assert transport.created_model_count == 1


def test_walkthrough_emits_structured_lifecycle_events(tmp_path: Path) -> None:
    renderer = _RecordingRenderer()

    run_governed_replay(
        _configuration(tmp_path),
        RestClient("http://api.test", transport=_stateful_transport()),
        renderer=renderer,
    )

    names = [event.name for event in renderer.events]
    assert names[0] == "walkthrough_started"
    assert names[-1] == "walkthrough_completed"
    assert names.count("step_started") == 9
    assert names.count("step_completed") == 9
    assert {
        event.step_id for event in renderer.events if event.name == "step_started"
    } >= {
        "observe_prompt",
        "inspect_lineage",
        "submit_replay",
    }
    assert all(
        isinstance(event, WalkthroughLifecycleEvent) for event in renderer.events
    )


def test_interactive_submission_failure_preserves_the_prepared_replay(
    tmp_path: Path,
) -> None:
    configuration = WalkthroughConfiguration(
        **{
            **_configuration(tmp_path).__dict__,
            "submit_replay": True,
            "continue_after_submission_failure": True,
        }
    )

    manifest = run_governed_replay(
        configuration,
        RestClient("http://api.test", transport=_submission_failing_transport()),
    )

    submission = next(
        step for step in manifest.steps if step.step_id == "submit_replay"
    )
    assert manifest.outcome == "COMPLETED"
    assert submission.status == "FAILED"
    assert submission.result["reason"] == "Job queue capacity has been reached."
    assert any(step.step_id == "inspect_lineage" for step in manifest.steps)


def test_completed_idempotent_replay_is_not_submitted_again(tmp_path: Path) -> None:
    transport = _completed_replay_transport()
    configuration = WalkthroughConfiguration(
        **{**_configuration(tmp_path).__dict__, "submit_replay": True}
    )

    manifest = run_governed_replay(
        configuration, RestClient("http://api.test", transport=transport)
    )

    submission = next(
        step for step in manifest.steps if step.step_id == "submit_replay"
    )
    assert submission.status == "SKIPPED"
    assert submission.result["replay_status"] == "COMPLETED"
    assert transport.submission_attempted is False


def test_rich_renderer_includes_scorecard_and_learning_milestone(
    tmp_path: Path,
) -> None:
    manifest = run_governed_replay(
        _configuration(tmp_path),
        RestClient("http://api.test", transport=_stateful_transport()),
    )
    renderer = RichRenderer(no_color=True)
    renderer.console = Console(record=True, force_terminal=False)

    renderer.render_manifest(manifest)

    output = renderer.console.export_text()
    assert "Mission Summary" in output
    assert "Prompt observed" in output
    assert "Manifest written" in output
    assert "Duration" in output
    assert "Governance Explorer" in output


def test_manifest_cleanup_requires_explicit_apply(tmp_path: Path) -> None:
    manifests = tmp_path / ".ai-governance" / "walkthroughs"
    manifests.mkdir(parents=True)
    old = manifests / "old.json"
    recent = manifests / "recent.json"
    old.write_text("{}")
    recent.write_text("{}")
    old_timestamp = 0
    os.utime(old, (old_timestamp, old_timestamp))

    preview = cleanup_walkthrough_manifests(root=tmp_path, older_than_days=7)
    assert preview.candidates == [str(old)]
    assert preview.removed == []
    assert old.exists()

    applied = cleanup_walkthrough_manifests(
        root=tmp_path, older_than_days=7, apply=True
    )
    assert applied.removed == [str(old)]
    assert not old.exists()
    assert recent.exists()


def _configuration(
    tmp_path: Path, *, manifest_path: Path | None = None
) -> WalkthroughConfiguration:
    return WalkthroughConfiguration(
        api_url="http://api.test",
        studio_url="http://studio.test",
        organization_id="org_test",
        project_id="project_test",
        manifest_path=manifest_path or tmp_path / "first.json",
    )


class _read_only_walkthrough_transport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, path, query, body):
        self.calls.append((method, path))
        responses = {
            "/api/v1/replay-executions/search": {
                "items": [{"execution_id": "execution-1", "replayable": True}]
            },
            "/api/v1/evaluations/history/execution-1": {
                "evaluations": [{"evaluation_id": "evaluation-1"}]
            },
            "/api/v1/evaluations/evaluation-1": {
                "evaluation_id": "evaluation-1",
                "evaluator_type": "quality",
            },
            "/api/v1/policy-schema": {"target_types": [{"name": "prompt"}]},
            "/api/v1/policies": [
                {"policy_id": "policy-1", "name": "Quality gate", "status": "ACTIVE"}
            ],
            "/api/v1/policies/policy-1": {
                "policy_id": "policy-1",
                "active_version": 1,
                "versions": [{"version": 1}],
            },
            "/api/v1/decisions": {"decisions": [{"decision_id": "decision-1"}]},
            "/api/v1/decisions/decision-1/detail": {"audit_records": []},
            "/api/v1/decisions/decision-1/explanation": {
                "decision_id": "decision-1",
                "summary": "Approved",
            },
            "/api/v1/experiments": [
                {
                    "experiment_id": "experiment-1",
                    "name": "Baseline",
                    "status": "COMPLETED",
                }
            ],
            "/api/v1/experiments/experiment-1/candidates": [
                {"candidate_id": "candidate-1"}
            ],
            "/api/v1/experiments/experiment-1/insights": {
                "status": "SUCCEEDED",
                "summary": "Candidate evidence inspected.",
            },
        }
        try:
            return responses[path]
        except KeyError as exc:
            raise AssertionError(
                f"Unexpected public API call: {method} {path}"
            ) from exc


class _stateful_transport:
    def __init__(self, *, fail_dataset_once: bool = False) -> None:
        self.fail_dataset_once = fail_dataset_once
        self.created_prompt_count = 0
        self.created_model_count = 0
        self.created_replay_count = 0

    def __call__(self, method, path, query, body):
        if path == "/api/v1/prompts/observations":
            if not self.created_prompt_count:
                self.created_prompt_count += 1
            return {
                "prompt_id": "prompt-walkthrough-v1",
                "name": "prompt",
                "version": "v1",
            }
        if path == "/api/v1/models/observations":
            if not self.created_model_count:
                self.created_model_count += 1
            return {"model_id": "model-walkthrough-v1"}
        if path == "/api/v1/datasets":
            if self.fail_dataset_once:
                self.fail_dataset_once = False
                raise RestClientError(status_code=503)
            return [{"dataset_id": "demo-dataset-evaluation"}]
        if path == "/api/v1/replay-executions/search":
            return {"items": [{"execution_id": "execution-1", "replayable": True}]}
        if path == "/api/v1/evaluations/history/execution-1":
            return {"evaluations": [{"evaluation_id": "evaluation-1"}]}
        if path == "/api/v1/decisions":
            return {"decisions": [{"decision_id": "decision-1"}]}
        if path == "/api/v1/decisions/decision-1/detail":
            return {"decision": {"status": "APPROVED"}, "audit_records": []}
        if path == "/api/v1/replays":
            if not self.created_replay_count:
                self.created_replay_count += 1
            return {
                "replay_id": "replay-1",
                "source_execution_id": "execution-1",
                "status": "READY",
                "mode": "FULL",
            }
        if path.endswith("/neighbourhood"):
            return {"nodes": [], "relationships": []}
        raise AssertionError(f"Unexpected public API call: {method} {path}")


class _RecordingRenderer:
    def __init__(self) -> None:
        self.events: list[WalkthroughLifecycleEvent] = []

    def emit(self, event: WalkthroughLifecycleEvent) -> None:
        self.events.append(event)

    def render_manifest(self, manifest) -> str:
        return ""


class _submission_failing_transport(_stateful_transport):
    def __call__(self, method, path, query, body):
        if path.endswith("/submit"):
            raise RestClientError(
                status_code=400,
                payload={"error": {"message": "Job queue capacity has been reached."}},
            )
        return super().__call__(method, path, query, body)


class _completed_replay_transport(_stateful_transport):
    def __init__(self) -> None:
        super().__init__()
        self.submission_attempted = False

    def __call__(self, method, path, query, body):
        if path == "/api/v1/replays":
            return {
                "replay_id": "replay-1",
                "source_execution_id": "execution-1",
                "status": "COMPLETED",
                "mode": "FULL",
            }
        if path.endswith("/submit"):
            self.submission_attempted = True
            raise AssertionError("A completed replay must not be submitted again.")
        return super().__call__(method, path, query, body)
