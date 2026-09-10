"""Repository-owned, package-resolvable Inspect tasks and solvers.

These are deliberately small integration fixtures.  They prove that the API
and worker load task code from the same installed ai-governance artifact; they
are not representative agent benchmarks.
"""

from __future__ import annotations

import hashlib
import json

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser
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

from ai_governance.evaluation.scaffold_artifacts import (
    SCAFFOLD_PLAN_SCHEMA_VERSION,
    SCAFFOLD_PLAN_STORE_KEY,
)

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


_PLANNER_EXECUTOR_SAMPLES = (
    (
        (
            "A route starts at 18 km. It travels 7 km north, then 4 km south, then 6 km north. "
            "How many kilometres north of the start is it? Reply with only the number."
        ),
        "9",
    ),
    (
        (
            "A team has 48 tickets. It resolves 15, receives 9 new tickets, then splits the "
            "remaining tickets equally between 3 agents. How many tickets does each agent get? "
            "Reply with only the number."
        ),
        "14",
    ),
    (
        (
            "A recipe needs 3 cups of flour for 8 servings. How many cups are needed for 24 "
            "servings? Reply with only the number."
        ),
        "9",
    ),
    (
        (
            "A train leaves at 09:35 and travels for 1 hour 47 minutes. What is its arrival time "
            "in 24-hour HH:MM format? Reply with only the time."
        ),
        "11:22",
    ),
    (
        (
            "A store discounts a $80 item by 25%, then adds a fixed $6 delivery fee. What is the "
            "final price in dollars? Reply with only the number."
        ),
        "66",
    ),
    (
        (
            "Three boxes contain 12, 18, and 24 pencils. After giving away 9 pencils from the "
            "total, the rest are shared equally among 3 students. How many pencils does each "
            "student receive? Reply with only the number."
        ),
        "15",
    ),
    (
        (
            "A library has 120 books. Two fifths are fiction. One quarter of the fiction books are "
            "on loan. How many fiction books are still on the shelf? Reply with only the number."
        ),
        "36",
    ),
    (
        (
            "A password uses one letter followed by two digits. The letter is the third letter after "
            "C and the digits are 4 doubled then decreased by 1. Write the password with no spaces."
        ),
        "F87",
    ),
    (
        (
            "A tank is 3/5 full. After adding 24 litres it is 9/10 full. What is the tank capacity "
            "in litres? Reply with only the number."
        ),
        "80",
    ),
    (
        (
            "Mia saves $5 each weekday for 3 weeks, then spends $18. Assume 5 weekdays per week. "
            "How many dollars remain? Reply with only the number."
        ),
        "57",
    ),
)


def _structured_plan(raw_plan: str) -> str:
    """Validate a bounded, non-hidden plan before the executor consumes it."""
    try:
        candidate = json.loads(raw_plan)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Planner output must be a JSON object with a steps array."
        ) from exc
    steps = candidate.get("steps") if isinstance(candidate, dict) else None
    if (
        not isinstance(steps, list)
        or not 1 <= len(steps) <= 3
        or any(
            not isinstance(step, str) or not step.strip() or len(step) > 240
            for step in steps
        )
    ):
        raise ValueError(
            "Planner output must contain one to three non-empty steps of at most 240 characters."
        )
    return json.dumps(
        {"steps": [step.strip() for step in steps]},
        separators=(",", ":"),
        ensure_ascii=False,
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
def planning_instruction_generate(planning_prompt_version: str = "v1") -> Solver:
    """One-call planning-instruction prompt variant for integration smoke tests.

    This deliberately changes the instruction before one ``generate`` call. It
    is not a planner–executor scaffold and must not be used to claim two-stage
    planning overhead. ``v1`` remains explicit in candidate provenance.
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


@solver
def plan_then_generate(planning_prompt_version: str = "v1") -> Solver:
    """Backward-compatible name for historical smoke-run replay only."""
    return planning_instruction_generate(planning_prompt_version)


@solver
def planner_executor_generate(
    plan_schema_version: str = SCAFFOLD_PLAN_SCHEMA_VERSION,
) -> Solver:
    """Generate a short explicit plan, then execute it in a second model call."""
    if plan_schema_version != SCAFFOLD_PLAN_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported plan_schema_version; the packaged planner–executor scaffold "
            f"supports {SCAFFOLD_PLAN_SCHEMA_VERSION}."
        )

    async def solve(state: TaskState, model_generate: Generate) -> TaskState:
        original_task = state.input_text
        state.user_prompt.text = (
            "Create a short execution plan for the task below. Return only a JSON object "
            'with this shape: {"steps": ["step 1", "step 2"]}. Use at most three short '
            "steps. Do not answer the task.\n\n"
            f"Task:\n{original_task}"
        )
        state = await model_generate(state, tool_calls="none")
        plan = _structured_plan(state.output.completion)
        state.store.set(
            SCAFFOLD_PLAN_STORE_KEY,
            {
                "schema_version": plan_schema_version,
                "content_digest": hashlib.sha256(plan.encode()).hexdigest(),
                "stage": "planning",
            },
        )
        state.messages.append(
            ChatMessageUser(
                content=(
                    "Solve the original task using the explicit plan below. Return only the "
                    "requested final answer and follow its output format exactly.\n\n"
                    f"Original task:\n{original_task}\n\n"
                    f"Plan:\n{plan}"
                )
            )
        )
        return await model_generate(state, tool_calls="none")

    return solve


@task
def planner_executor_smoke() -> Task:
    """Ten deterministic multi-step samples for a two-call scaffold experiment."""
    return Task(
        dataset=[
            Sample(id=index, input=prompt, target=answer)
            for index, (prompt, answer) in enumerate(_PLANNER_EXECUTOR_SAMPLES, start=1)
        ],
        solver=generate(),
        scorer=exact(),
        name="ai_governance_planner_executor_smoke",
        version=1,
        metadata={
            "task_version": "planner-executor-smoke-v1",
            "sample_count": len(_PLANNER_EXECUTOR_SAMPLES),
            "expected_baseline_model_calls_per_sample": 1,
            "expected_planner_model_calls_per_sample": 2,
        },
    )


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
        (
            "Call controlled_evidence_lookup with capital, then answer only the result.",
            "Canberra",
        ),
        ("Answer only blue. Do not call a tool.", "blue"),
        (
            "Call controlled_flaky_lookup with first, then recovery, then answer only the recovered result.",
            "RECOVERED_EVIDENCE",
        ),
        (
            "Make at most one tool call. Call controlled_evidence_lookup with number and answer only the result.",
            "seven",
        ),
    )
    return Task(
        dataset=[
            Sample(id=index, input=prompt, target=target)
            for index, (prompt, target) in enumerate(samples, start=1)
        ],
        solver=controlled_trajectory_solver(),
        scorer=exact(),
        name="ai_governance_trajectory_fidelity_smoke",
        version=1,
        metadata={
            "task_version": "trajectory-fidelity-v1",
            "deterministic_tools": True,
        },
    )
