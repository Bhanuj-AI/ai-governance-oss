"""Command-line entry point for Kavach guided walkthroughs."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version

from dotenv import load_dotenv

from kavach.cli.walkthrough import (
    WalkthroughConfiguration,
    WalkthroughError,
    cleanup_walkthrough_manifests,
    format_cleanup,
    run_evaluation_pipeline,
    run_decision_detective,
    run_experiment_arena,
    run_governed_replay,
    run_policy_gate,
)
from kavach.cli.walkthrough_renderers import (
    JsonRenderer,
    PlainRenderer,
    RichRenderer,
    WalkthroughRenderer,
)
from kavach.mcp.authentication import StaticBearerAuthenticationContext
from kavach.mcp.clients import RestClient, RestClientError
from kavach.oauth import OAuthClientCredentialsError, access_token_from_environment


def main() -> None:
    """Run one of the intentionally small set of supported walkthroughs."""
    load_dotenv(Path(".env.local"), override=False)
    load_dotenv(Path(".env.oauth.generated"), override=False)
    parser = _parser()
    arguments = parser.parse_args()

    if arguments.command == "walkthrough" and arguments.walkthrough == "list":
        print(
            "governed-replay      Record observed assets and prepare a governed replay."
        )
        print("evaluation-pipeline  Inspect immutable evaluation history and metrics.")
        print("policy-gate          Inspect policy schema, versions, and rules.")
        print("decision-detective   Trace persisted governance decisions and evidence.")
        print("experiment-arena     Inspect experiment candidates and outcomes.")
        return

    if arguments.command == "walkthrough" and arguments.walkthrough == "cleanup":
        try:
            result = cleanup_walkthrough_manifests(
                older_than_days=arguments.older_than_days,
                apply=arguments.apply,
            )
        except WalkthroughError as exc:
            parser.exit(1, f"Walkthrough cleanup failed: {exc}\n")
        print(format_cleanup(result, output_json=arguments.output_json))
        return

    if arguments.command != "walkthrough" or arguments.walkthrough not in {
        "governed-replay",
        "evaluation-pipeline",
        "policy-gate",
        "decision-detective",
        "experiment-arena",
    }:
        parser.error("Choose a supported walkthrough. Run 'kavach walkthrough list'.")

    if arguments.output_json and arguments.interactive:
        parser.error("--interactive cannot be combined with --output-json.")
    if arguments.non_interactive and arguments.interactive:
        parser.error("--interactive cannot be combined with --non-interactive.")

    renderer = _renderer_for(arguments)
    if (
        isinstance(renderer, RichRenderer)
        and arguments.interactive
        and arguments.walkthrough in {"governed-replay", "evaluation-pipeline"}
    ):
        renderer.offer_manifest_cleanup()
    configuration = WalkthroughConfiguration(
        api_url=arguments.api_url,
        studio_url=arguments.studio_url,
        organization_id=arguments.organization_id,
        project_id=arguments.project_id,
        source_execution_id=getattr(arguments, "source_execution_id", None),
        submit_replay=getattr(arguments, "submit_replay", False),
        continue_after_submission_failure=arguments.interactive,
        manifest_path=Path(arguments.manifest) if arguments.manifest else None,
    )
    try:
        token = _resolve_walkthrough_token(arguments.token)
    except WalkthroughError as exc:
        parser.exit(1, f"Walkthrough authentication failed: {exc}\n")
    client = RestClient(
        configuration.api_url,
        authentication_context=StaticBearerAuthenticationContext(token),
    ).with_tenant_context(configuration.organization_id, configuration.project_id)

    if (
        isinstance(renderer, RichRenderer)
        and arguments.interactive
        and arguments.walkthrough in {"governed-replay", "evaluation-pipeline"}
    ):
        if configuration.source_execution_id is None:
            try:
                source_execution_id = renderer.select_source_execution(client)
            except RestClientError as exc:
                parser.exit(1, f"Walkthrough source selection failed: {exc}\n")
            if source_execution_id:
                configuration = WalkthroughConfiguration(
                    **{
                        **configuration.__dict__,
                        "source_execution_id": source_execution_id,
                    }
                )
        if (
            arguments.walkthrough == "governed-replay"
            and not configuration.submit_replay
        ):
            configuration = WalkthroughConfiguration(
                **{
                    **configuration.__dict__,
                    "submit_replay": renderer.confirm_replay_submission(),
                    "continue_after_submission_failure": True,
                }
            )

    try:
        manifest = (
            run_evaluation_pipeline(configuration, client, renderer=renderer)
            if arguments.walkthrough == "evaluation-pipeline"
            else run_policy_gate(configuration, client, renderer=renderer)
            if arguments.walkthrough == "policy-gate"
            else run_decision_detective(configuration, client, renderer=renderer)
            if arguments.walkthrough == "decision-detective"
            else run_experiment_arena(configuration, client, renderer=renderer)
            if arguments.walkthrough == "experiment-arena"
            else run_governed_replay(configuration, client, renderer=renderer)
        )
    except WalkthroughError as exc:
        parser.exit(1, f"Walkthrough failed: {exc}\n")

    output = renderer.render_manifest(manifest)
    if output is not None:
        print(output)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kavach",
        description="Guided Kavach product walkthroughs that use only public REST APIs.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    walkthrough = commands.add_parser(
        "walkthrough",
        help="Run or maintain a guided scenario.",
    )
    scenarios = walkthrough.add_subparsers(dest="walkthrough", required=True)

    scenarios.add_parser("list", help="List the available walkthrough scenarios.")

    cleanup = scenarios.add_parser(
        "cleanup",
        help="Preview or remove aged local walkthrough manifests.",
    )
    cleanup.add_argument(
        "--older-than-days",
        type=int,
        default=7,
        help="Select manifests older than this many days (default: 7).",
    )
    cleanup.add_argument(
        "--apply",
        action="store_true",
        help="Delete selected manifests after showing the preview.",
    )
    cleanup.add_argument(
        "--output-json",
        action="store_true",
        help="Write the cleanup result as JSON.",
    )

    replay = scenarios.add_parser(
        "governed-replay",
        help="Record observed assets, inspect evidence, and prepare a replay.",
    )
    replay.add_argument(
        "--api-url", default=os.getenv("KAVACH_API_URL", "http://localhost:8000")
    )
    replay.add_argument(
        "--studio-url", default=os.getenv("KAVACH_STUDIO_URL", "http://localhost:3000")
    )
    replay.add_argument(
        "--organization-id",
        default=os.getenv("KAVACH_ORGANIZATION_ID", "org_default"),
    )
    replay.add_argument(
        "--project-id", default=os.getenv("KAVACH_PROJECT_ID", "project_default")
    )
    replay.add_argument(
        "--token",
        help="Explicit bearer-token override. By default the CLI uses KAVACH_OAUTH_* credentials.",
    )
    replay.add_argument("--source-execution-id")
    replay.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts (the initial golden path is deterministic by default).",
    )
    replay.add_argument(
        "--interactive",
        action="store_true",
        help="Use the guided terminal experience and ask only optional questions.",
    )
    replay.add_argument(
        "--theme",
        choices=("retro",),
        help="Use an opt-in visual theme (currently: retro).",
    )
    replay.add_argument(
        "--no-color",
        action="store_true",
        help="Disable terminal colour in the guided experience.",
    )
    replay.add_argument(
        "--submit-replay",
        action="store_true",
        help="Queue the prepared replay. It is not submitted by default.",
    )
    replay.add_argument(
        "--manifest", help="Write the run manifest to this path instead of .kavach/."
    )
    replay.add_argument(
        "--output-json",
        "--json",
        dest="output_json",
        action="store_true",
        help="Write the complete run manifest as JSON to stdout.",
    )
    evaluation = scenarios.add_parser(
        "evaluation-pipeline",
        help="Inspect immutable evaluation evidence and metric records.",
    )
    for action in replay._actions:
        if action.dest in {"help", "submit_replay"}:
            continue
        evaluation._add_action(action)
    evaluation.set_defaults(submit_replay=False)
    policy = scenarios.add_parser(
        "policy-gate", help="Inspect policy schema, versions, and rules."
    )
    for action in replay._actions:
        if action.dest in {"help", "submit_replay", "source_execution_id"}:
            continue
        policy._add_action(action)
    policy.set_defaults(submit_replay=False, source_execution_id=None)
    detective = scenarios.add_parser(
        "decision-detective", help="Trace decision evidence and explanations."
    )
    for action in policy._actions:
        if action.dest != "help":
            detective._add_action(action)
    detective.set_defaults(submit_replay=False, source_execution_id=None)
    arena = scenarios.add_parser(
        "experiment-arena",
        help="Inspect experiment candidates and outcome evidence.",
    )
    for action in policy._actions:
        if action.dest != "help":
            arena._add_action(action)
    arena.set_defaults(submit_replay=False, source_execution_id=None)
    return parser


def _renderer_for(arguments: argparse.Namespace) -> WalkthroughRenderer:
    if arguments.output_json:
        return JsonRenderer()
    if arguments.interactive or arguments.theme:
        return RichRenderer(
            no_color=arguments.no_color,
            theme=arguments.theme,
            interactive=arguments.interactive,
        )
    return PlainRenderer()


def _resolve_walkthrough_token(explicit_token: str | None) -> str | None:
    """Prefer caller identity, otherwise use configured workload credentials.

    Client credentials are appropriate for local walkthroughs and automation;
    the resulting JWT represents the configured service account, never an
    impersonated organization administrator or user.
    """
    if explicit_token:
        return explicit_token
    if os.getenv("KAVACH_AUTH_MODE", "").lower() == "development":
        return None
    try:
        return access_token_from_environment()
    except OAuthClientCredentialsError as exc:
        raise WalkthroughError(
            "Could not obtain a walkthrough service-account token. "
            "Complete KAVACH_OAUTH_* client credentials or pass --token explicitly. "
            f"Details: {exc}"
        ) from exc


def _package_version() -> str:
    try:
        return version("kavach")
    except PackageNotFoundError:
        return "unknown"
