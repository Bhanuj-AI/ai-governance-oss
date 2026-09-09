"""Repository-owned, package-resolvable Inspect tasks and solvers.

These are deliberately small integration fixtures.  They prove that the API
and worker load task code from the same installed ai-governance artifact; they
are not representative agent benchmarks.
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import exact
from inspect_ai.solver import (
    Generate,
    Solver,
    TaskState,
    chain,
    generate,
    solver,
    use_tools,
)
from inspect_ai.tool import Tool, tool

_SMOKE_SAMPLES = (
    ("What is 1 + 1? Reply with only the number.", "2"),
    ("What is 3 + 4? Reply with only the number.", "7"),
    ("What is 5 - 2? Reply with only the number.", "3"),
    ("What is 6 / 2? Reply with only the number.", "3"),
    ("What is 4 * 3? Reply with only the number.", "12"),
    ("What is the next letter after A? Reply with only the letter.", "B"),
    ("What is the first month of the year? Reply with only the word.", "January"),
    ("How many days are in a week? Reply with only the number.", "7"),
    ("What color is a clear daytime sky? Reply with only the word.", "blue"),
    ("What is the opposite of hot? Reply with only the word.", "cold"),
)


@task
def scaffold_smoke() -> Task:
    """Ten deterministic exact-answer samples for runner integration checks."""
    return Task(
        dataset=[
            Sample(id=index, input=prompt, target=answer)
            for index, (prompt, answer) in enumerate(_SMOKE_SAMPLES, start=1)
        ],
        solver=generate(),
        scorer=exact(),
        name="ai_governance_scaffold_smoke",
        version=1,
        metadata={"task_version": "smoke-v1", "sample_count": len(_SMOKE_SAMPLES)},
    )


@solver
def plan_then_generate(planning_prompt_version: str = "v1") -> Solver:
    """A packaged scaffold that requires a silent plan before final generation.

    It intentionally differs from ``generate`` by transforming the task prompt
    before calling Inspect's supported generation solver.  ``v1`` is explicit
    in candidate provenance so future prompt changes are distinguishable.
    """
    if planning_prompt_version != "v1":
        raise ValueError(
            "Unsupported planning_prompt_version; the packaged smoke scaffold supports v1."
        )

    async def solve(state: TaskState, model_generate: Generate) -> TaskState:
        state.user_prompt.text = (
            "Make a short internal plan before solving the request. Do not reveal "
            "the plan. Follow the requested output format exactly.\n\n"
            f"{state.user_prompt.text}"
        )
        return await model_generate(state)

    return solve


@tool
def controlled_evidence_lookup() -> Tool:
    """Return deterministic, referenceable evidence for the fidelity fixture."""

    async def execute(query: str) -> str:
        """Look up one controlled fact by its fixed fixture key.

        Args:
            query: Fixture key: ``capital``, ``colour``, or ``number``.
        """
        values = {"capital": "Canberra", "colour": "blue", "number": "seven"}
        return values.get(query.strip().lower(), "NOT_FOUND")

    return execute


@tool
def controlled_flaky_lookup() -> Tool:
    """Fail once on the explicit first-attempt key, then return fixed evidence."""

    async def execute(attempt: str) -> str:
        """Use ``first`` to exercise a bounded tool failure, then ``recovery``.

        Args:
            attempt: ``first`` fails deterministically; ``recovery`` succeeds.
        """
        if attempt.strip().lower() == "first":
            raise RuntimeError("controlled_lookup_failure")
        if attempt.strip().lower() == "recovery":
            return "RECOVERED_EVIDENCE"
        return "NOT_FOUND"

    return execute


@solver
def controlled_trajectory_solver() -> Solver:
    """Use real deterministic tools before generation for fidelity experiments.

    The task prompts prescribe the bounded tool behaviour.  Inspect emits the
    resulting model/tool/error events; the control plane records only safe
    event facts and immutable digests, never the tool payload itself.
    """
    return chain(
        use_tools(
            controlled_evidence_lookup(),
            controlled_flaky_lookup(),
            tool_choice="any",
        ),
        generate(),
    )


@task
def trajectory_fidelity_smoke() -> Task:
    """Small controlled task set that exercises observable tool behaviour.

    It is an integration fixture, not a benchmark.  A deterministic local
    tool provides evidence and a controlled failure/recovery route without a
    paid external service.  The bounded prompt prevents unbounded retries.
    """
    samples = (
        ("Call controlled_evidence_lookup with capital, then answer only the result.", "Canberra"),
        ("Answer only blue. Do not call a tool.", "blue"),
        ("Call controlled_flaky_lookup with first, then recovery, then answer only the recovered result.", "RECOVERED_EVIDENCE"),
        ("Make at most one tool call. Call controlled_evidence_lookup with number and answer only the result.", "seven"),
    )
    return Task(
        dataset=[Sample(id=index, input=prompt, target=target) for index, (prompt, target) in enumerate(samples, start=1)],
        solver=controlled_trajectory_solver(),
        scorer=exact(),
        name="ai_governance_trajectory_fidelity_smoke",
        version=1,
        metadata={"task_version": "trajectory-fidelity-v1", "deterministic_tools": True},
    )
