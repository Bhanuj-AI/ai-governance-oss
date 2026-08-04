"""Presentation adapters for guided walkthrough lifecycle events.

The walkthrough engine emits data-only events.  These adapters decide whether
that data becomes stable plain text, JSON, or an opt-in terminal experience.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

if TYPE_CHECKING:
    from kavach.cli.walkthrough import WalkthroughLifecycleEvent, WalkthroughManifest
    from kavach.cli.walkthrough import WalkthroughClient


class WalkthroughRenderer(Protocol):
    """A presentation boundary for a deterministic walkthrough run."""

    def emit(self, event: WalkthroughLifecycleEvent) -> None: ...

    def render_manifest(self, manifest: WalkthroughManifest) -> str | None: ...


class PlainRenderer:
    """Preserve the established concise output for scripts and CI logs."""

    def emit(self, event: WalkthroughLifecycleEvent) -> None:
        return None

    def render_manifest(self, manifest: WalkthroughManifest) -> str:
        from kavach.cli.walkthrough import format_walkthrough

        return format_walkthrough(manifest, output_json=False)


class JsonRenderer:
    """Render the complete manifest without lifecycle noise on stdout."""

    def emit(self, event: WalkthroughLifecycleEvent) -> None:
        return None

    def render_manifest(self, manifest: WalkthroughManifest) -> str:
        return json.dumps(manifest.to_dict(), indent=2, sort_keys=True, default=str)


class RichRenderer:
    """An opt-in retro-platform quest presentation using Rich primitives."""

    _STATUS = {
        "COMPLETED": "✅",
        "SKIPPED": "⏭",
        "PENDING": "⏳",
        "PENDING_PROJECTION": "⏳",
        "QUEUED": "🚀",
        "NOT_REQUESTED": "🔒",
        "FAILED": "❌",
    }

    def __init__(
        self,
        *,
        no_color: bool = False,
        theme: str | None = None,
        interactive: bool = False,
    ) -> None:
        self.console = Console(no_color=no_color)
        self.theme = theme
        self.interactive = interactive
        self._step_total = 0
        self._step_number = 0
        self._progress: Progress | None = None
        self._progress_task: TaskID | None = None

    def emit(self, event: WalkthroughLifecycleEvent) -> None:
        if event.name == "walkthrough_started":
            self._step_total = int(event.data.get("step_count", 0))
            title = event.data.get("title", "Kavach Walkthrough")
            subtitle = (
                f"World {event.data.get('world', '1-1')}: "
                f"{event.data.get('level_title', 'Get Started')}"
                if self.theme == "retro"
                else f"{event.data.get('category', 'general').title()} walkthrough"
            )
            self.console.print()
            self._render_hud(event)
            self.console.print()
            self.console.print(
                Panel(
                    f"[bold cyan]KAVACH GOVERNED REPLAY QUEST[/]\n[dim]{subtitle}[/]",
                    title=title,
                    border_style="cyan",
                    padding=(1, 4),
                )
            )
            self.console.print()
            self.console.print(f"🍄 Tenant detected: [bold]{event.tenant_id}[/]")
            self.console.print(f"⭐ Scenario: [bold]{title}[/]")
            self.console.print("🔐 Public API mode: [green]enabled[/]")
            self.console.print()
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console,
                transient=True,
            )
            self._progress_task = self._progress.add_task(
                "Evidence checks", total=self._step_total
            )
            self._progress.start()
        elif event.name == "step_started" and event.step_id != "submit_replay":
            self._step_number += 1
            if self._progress is not None and self._progress_task is not None:
                self._progress.update(
                    self._progress_task,
                    description=f"Level {self._step_number}: {event.action}",
                )
        elif event.name == "step_failed":
            if event.step_id == "submit_replay":
                return
            self.console.print(
                f"[red]Walkthrough failed: {event.data.get('message', 'Unknown error')}[/]"
            )
        elif event.name in {"step_completed", "step_skipped"}:
            if event.step_id == "submit_replay":
                return
            if self._progress is not None and self._progress_task is not None:
                self._progress.advance(self._progress_task)
            status = self._STATUS.get(event.status or "", "•")
            self.console.print(f"{status} {event.action or event.step_id}")
            self.console.print(f"      [dim]{self._detail(event)}[/]")
            if event.inspect_url:
                self.console.print(
                    f"      [link={event.inspect_url}]Inspect in Studio[/link]"
                )
                self._offer_step_actions(event.inspect_url)
            self.console.print()

    def render_manifest(self, manifest: WalkthroughManifest) -> None:
        if self._progress is not None:
            self._progress.stop()
        self.console.print()
        self.console.print(
            Panel(
                "[bold green]🏁 QUEST COMPLETE[/]", border_style="green", padding=(1, 4)
            )
        )
        self.console.print()
        submission = next(
            (step for step in manifest.steps if step.step_id == "submit_replay"), None
        )
        if submission is not None and submission.status == "FAILED":
            self.console.print(
                f"[yellow]Boss gate unavailable:[/] {submission.result.get('reason', 'Submission failed.')}"
            )
        elif submission is not None and submission.status == "SKIPPED":
            self.console.print(
                f"[cyan]Boss gate checkpoint:[/] {submission.result.get('reason', 'Submission was not needed.')}"
            )
        elif not manifest.resources.get("replay_job_id"):
            self.console.print("Replay prepared but not submitted.")
        self._render_scorecard(manifest)
        self._render_achievement(manifest)
        return None

    def _render_hud(self, event: WalkthroughLifecycleEvent) -> None:
        """Render an original, roomy platform-quest status display."""
        hud = Table.grid(expand=True, padding=(0, 3))
        hud.add_column(justify="left")
        hud.add_column(justify="center")
        hud.add_column(justify="center")
        hud.add_column(justify="right")
        hud.add_row(
            "[bold cyan]KAVACH QUEST[/]",
            f"[bold yellow]COINS[/] 0/{self._step_total}",
            f"[bold magenta]WORLD[/] {event.data.get('world', '1-1')}",
            "[bold green]CHECKPOINT[/] 0%",
        )
        self.console.print(Panel(hud, border_style="blue", padding=(1, 2)))

    def select_source_execution(self, client: WalkthroughClient) -> str | None:
        """Offer a bounded, optional selection without changing engine semantics."""
        page = client.get(
            "/api/v1/replay-executions/search",
            query={"replayable_only": True, "limit": 10},
        )
        items = page.get("items", []) if isinstance(page, Mapping) else []
        choices = [
            item
            for item in items
            if isinstance(item, Mapping) and item.get("execution_id")
        ]
        if not choices:
            return None
        table = Table(title="Replayable executions")
        table.add_column("#", justify="right")
        table.add_column("Execution")
        table.add_column("Workflow")
        for index, item in enumerate(choices, start=1):
            table.add_row(
                str(index),
                str(item["execution_id"]),
                str(item.get("workflow_name", "—")),
            )
        self.console.print(table)
        selected = Prompt.ask(
            "Source execution",
            choices=[str(index) for index in range(1, len(choices) + 1)],
            default="1",
        )
        return str(choices[int(selected) - 1]["execution_id"])

    def offer_manifest_cleanup(self) -> None:
        """Make aged local checkpoint cleanup an explicit, reversible-to-decline choice."""
        from kavach.cli.walkthrough import cleanup_walkthrough_manifests

        preview = cleanup_walkthrough_manifests()
        if not preview.candidates:
            return
        self.console.print(
            f"[yellow]Found {len(preview.candidates)} aged local checkpoint(s).[/]"
        )
        if Confirm.ask("Clear those old checkpoints?", default=False):
            result = cleanup_walkthrough_manifests(apply=True)
            self.console.print(f"Cleared {len(result.removed)} checkpoint(s).")

    def confirm_replay_submission(self) -> bool:
        return Confirm.ask(
            "Boss gate: submit the prepared replay when ready?", default=False
        )

    def _offer_step_actions(self, url: str) -> None:
        if not self.interactive:
            return
        progress_was_running = self._progress is not None
        if self._progress is not None:
            self._progress.stop()
        try:
            self.console.print(
                "      [dim]Press O → Open in Studio · C → Copy URL · N → Continue[/]"
            )
            action = ""
            while action not in {"o", "c", "n"}:
                action = Prompt.ask("      Next action [O/C/N]", default="n").lower()
                if action not in {"o", "c", "n"}:
                    self.console.print("      [yellow]Choose O, C, or N.[/]")
        finally:
            if progress_was_running and self._progress is not None:
                self._progress.start()
        if action == "o":
            webbrowser.open(url)
        elif action == "c":
            if _copy_to_clipboard(url):
                self.console.print("      [green]URL copied.[/]")
            else:
                self.console.print(f"      [yellow]Copy unavailable; URL:[/] {url}")

    def _render_scorecard(self, manifest: WalkthroughManifest) -> None:
        self.console.print()
        self.console.rule("Mission Summary", style="cyan")
        steps = {step.step_id: step for step in manifest.steps}
        if manifest.walkthrough_id != "governed-replay":
            table = Table.grid(padding=(1, 4))
            table.add_column(style="bold")
            table.add_column()
            for step in manifest.steps:
                table.add_row(_score_status(step.status), step.action)
            table.add_row("✔", "Manifest written")
            table.add_row(
                "◷", f"Duration {_duration(manifest.started_at, manifest.completed_at)}"
            )
            self.console.print(table)
            self.console.print(f"[dim]Checkpoint:[/] {manifest.manifest_path}")
            self.console.print()
            return
        summary = (
            ("Prompt observed", "observe_prompt"),
            ("Model observed", "observe_model"),
            ("Dataset verified", "select_dataset"),
            ("Execution selected", "select_execution"),
            ("Baseline inspected", "inspect_baseline_evaluation"),
            ("Governance inspected", "inspect_decision"),
            ("Replay prepared", "create_replay"),
            ("Ontology verified", "inspect_lineage"),
        )
        table = Table.grid(padding=(1, 4))
        table.add_column(style="bold")
        table.add_column()
        for label, step_id in summary:
            step = steps.get(step_id)
            table.add_row(_score_status(step.status if step else None), label)
        submission = steps.get("submit_replay")
        table.add_row(
            _score_status(submission.status if submission else None),
            "Replay queued"
            if submission and submission.status == "QUEUED"
            else "Replay submission failed"
            if submission and submission.status == "FAILED"
            else "Replay checkpoint reused"
            if submission and submission.status == "SKIPPED"
            else "Replay prepared only",
        )
        table.add_row("✔", "Manifest written")
        table.add_row(
            "◷", f"Duration {_duration(manifest.started_at, manifest.completed_at)}"
        )
        self.console.print(table)
        self.console.print(f"[dim]Checkpoint:[/] {manifest.manifest_path}")
        self.console.print()

    def _render_achievement(self, manifest: WalkthroughManifest) -> None:
        achievements = {
            "evaluation-pipeline": (
                "Signal Seeker",
                "You traced immutable evaluation evidence through public APIs.",
            ),
            "policy-gate": (
                "Policy Pathfinder",
                "You mapped the rules behind a governance gate.",
            ),
            "decision-detective": (
                "Governance Explorer",
                "You inspected your first governance decision.",
            ),
            "experiment-arena": (
                "Benchmark Scout",
                "You inspected candidate evidence without changing an experiment.",
            ),
        }
        title, message = achievements.get(
            manifest.walkthrough_id,
            (
                "Governance Explorer"
                if manifest.resources.get("decision_id")
                else "Immutable Evidence",
                "You inspected your first governance decision."
                if manifest.resources.get("decision_id")
                else "You completed a governed replay using only public APIs.",
            ),
        )
        self.console.print(
            Panel.fit(
                f"[bold yellow]🏅 Achievement unlocked: {title}[/]\n{message}",
                border_style="yellow",
            )
        )

    @staticmethod
    def _detail(event: WalkthroughLifecycleEvent) -> str:
        result = event.data.get("result", {})
        if not isinstance(result, Mapping):
            return event.action or event.step_id or "Step completed"
        for key in (
            "prompt_id",
            "model_id",
            "dataset_id",
            "execution_id",
            "replay_id",
            "evaluation_id",
            "policy_id",
            "decision_id",
            "experiment_id",
        ):
            if value := result.get(key):
                return str(value)
        if reason := result.get("reason"):
            return str(reason)
        return event.action or event.step_id or "Step completed"


def _score_status(status: str | None) -> str:
    if status in {"COMPLETED", "QUEUED"}:
        return "✔"
    if status == "SKIPPED":
        return "↷"
    if status in {"PENDING", "PENDING_PROJECTION", "NOT_REQUESTED"}:
        return "◷"
    return "•"


def _duration(started_at: str, completed_at: str | None) -> str:
    if completed_at is None:
        return "—"
    duration = datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)
    return f"{duration.total_seconds():.1f}s"


def _copy_to_clipboard(value: str) -> bool:
    """Use the platform clipboard when available; never fail a walkthrough for it."""
    command = (
        ["pbcopy"]
        if sys.platform == "darwin"
        else ["clip"]
        if sys.platform == "win32"
        else ["wl-copy"]
        if shutil.which("wl-copy")
        else ["xclip", "-selection", "clipboard"]
        if shutil.which("xclip")
        else None
    )
    if command is None or shutil.which(command[0]) is None:
        return False
    try:
        subprocess.run(command, input=value, text=True, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True
