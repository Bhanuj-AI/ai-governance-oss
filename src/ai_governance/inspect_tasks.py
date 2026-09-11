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
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Target,
    accuracy,
    exact,
    scorer,
    stderr,
)
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

_INCIDENT_LENGTH_BANDS = (
    "short",
    "medium",
    "long",
    "extended",
    "xlong",
    "xxlong",
)
_INCIDENT_LENGTH_TARGETS = {
    "short": 50,
    "medium": 250,
    "long": 500,
    "extended": 1000,
    "xlong": 4600,
    "xxlong": 10_000,
}
_INCIDENT_TOKENIZER = "whitespace-token-estimate/v1"
_INCIDENT_PROMPT_VERSION = "incident-release-decision/v3"
_INCIDENT_PLAN_PROMPT_VERSION = "planner-executor-prompts/v1"

# Each case is a bounded, deterministic release decision. The supplemental
# records introduced by longer bands corroborate the same decision; they never
# change a policy threshold or expected outcome.
_INCIDENTS = (
    ("incident-01", "SEV1", "BLOCK", "DATA_ENGINEERING", ("FRESHNESS_BREACH", "PAYMENT_EXPORT"), "The scheduled payment export is 93 minutes late; policy blocks release after 30 minutes. Policy classification: severity SEV1, release BLOCK, owner DATA_ENGINEERING, reason codes FRESHNESS_BREACH and PAYMENT_EXPORT."),
    ("incident-02", "SEV2", "BLOCK", "DATA_GOVERNANCE", ("NULL_RATE_BREACH", "CUSTOMER_PROFILE"), "Customer-profile null rate is 7.4%; the governed maximum is 2.0%. Policy classification: severity SEV2, release BLOCK, owner DATA_GOVERNANCE, reason codes NULL_RATE_BREACH and CUSTOMER_PROFILE."),
    ("incident-03", "SEV2", "APPROVE_WITH_MONITORING", "DATA_ENGINEERING", ("RETRY_RECOVERED", "LATE_ARRIVAL"), "A late-arriving partition recovered after retry; freshness is now within the 30-minute threshold. Policy classification: severity SEV2, release APPROVE_WITH_MONITORING, owner DATA_ENGINEERING, reason codes RETRY_RECOVERED and LATE_ARRIVAL."),
    ("incident-04", "SEV3", "APPROVE", "DATA_ENGINEERING", ("NON_PRODUCTION_DELAY",), "A non-production analytics refresh was delayed 8 minutes and completed without data-quality drift. Policy classification: severity SEV3, release APPROVE, owner DATA_ENGINEERING, reason code NON_PRODUCTION_DELAY."),
    ("incident-05", "SEV1", "BLOCK", "SECURITY", ("PII_LINEAGE_GAP", "UNAPPROVED_SINK"), "Lineage shows a customer email field reaching an unapproved analytics sink. Policy classification: severity SEV1, release BLOCK, owner SECURITY, reason codes PII_LINEAGE_GAP and UNAPPROVED_SINK."),
    ("incident-06", "SEV2", "BLOCK", "DATA_GOVERNANCE", ("SCHEMA_BREAKING_CHANGE", "CONTRACT_VIOLATION"), "A required account-status field changed from an enumerated value to free text. Policy classification: severity SEV2, release BLOCK, owner DATA_GOVERNANCE, reason codes SCHEMA_BREAKING_CHANGE and CONTRACT_VIOLATION."),
    ("incident-07", "SEV3", "APPROVE_WITH_MONITORING", "DATA_ENGINEERING", ("VOLUME_ANOMALY", "THRESHOLD_NOT_BREACHED"), "Daily order volume is 18% above baseline but remains below the 25% release-block threshold. Policy classification: severity SEV3, release APPROVE_WITH_MONITORING, owner DATA_ENGINEERING, reason codes VOLUME_ANOMALY and THRESHOLD_NOT_BREACHED."),
    ("incident-08", "SEV2", "BLOCK", "SECURITY", ("ACCESS_CONTROL_FAILURE", "AUDIT_LOG_MISSING"), "The pipeline service account wrote customer data without the required audit event. Policy classification: severity SEV2, release BLOCK, owner SECURITY, reason codes ACCESS_CONTROL_FAILURE and AUDIT_LOG_MISSING."),
)


def _decision_target(severity: str, decision: str, owner: str, reasons: tuple[str, ...]) -> str:
    return json.dumps(
        {
            "severity": severity,
            "release_decision": decision,
            "escalation_owner": owner,
            "reason_codes": list(reasons),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _incident_prompt(summary: str, length_band: str) -> str:
    """Build an evidence-rich, semantically stable incident representation."""
    prompt = (
        "You are the governed release decision service for a scheduled customer-data pipeline. "
        f"Incident brief: {summary} "
        "Return JSON only with exactly severity, release_decision, escalation_owner, and reason_codes. "
        "Use severity SEV1|SEV2|SEV3; release_decision BLOCK|APPROVE_WITH_MONITORING|APPROVE; "
        "escalation_owner DATA_ENGINEERING|DATA_GOVERNANCE|SECURITY; and uppercase reason_codes."
        " Copy every value from the Policy classification exactly; do not add codes."
    )
    evidence = (
        " Contract: customer records require schema validation before publication."
        " Lineage: source ingestion flows through validation into the governed release gate."
        " Ownership: the listed escalation owner is on call for this policy category."
        " Timeline: detection, validation, and release-gate observations agree with the incident brief."
        " Quality records: corroborating checks did not introduce a conflicting threshold breach."
        " Downstream impact: affected consumers remain protected when the stated release decision is applied."
        " Audit record: the policy version and lineage references were reviewed for this release window."
        " Operations record: retries, acknowledgements, and monitoring observations are consistent with the brief."
    )
    target = _INCIDENT_LENGTH_TARGETS[length_band]
    if length_band == "short":
        return (
            prompt
            + " Apply the stated release threshold and preserve the listed operational owner."
        )
    detail_count = {
        "medium": 3,
        "long": 6,
        "extended": 8,
        "xlong": 8,
        "xxlong": 8,
    }[length_band]
    prompt += "".join(evidence.split(".")[:detail_count]) + "."
    # Add distinct, realistic corroborating records until the documented
    # estimate reaches the band. They are intentionally observational: the
    # policy classification in the brief remains the sole decision source.
    record_templates = (
        " Evidence ledger {record}: ingestion monitor recorded a retained event for the same release window; its observed state matches the incident brief.",
        " Evidence ledger {record}: validation audit retained the applicable contract and schema snapshot with no conflicting classification.",
        " Evidence ledger {record}: lineage checkpoint linked the governed source, validation stage, and release gate described in the brief.",
        " Evidence ledger {record}: on-call acknowledgement confirms the stated escalation owner reviewed the recorded policy category.",
        " Evidence ledger {record}: downstream protection monitor recorded the release action already specified by the policy classification.",
        " Evidence ledger {record}: observability archive retained timing and acknowledgement facts without changing a threshold or reason code.",
        " Evidence ledger {record}: change-management record references the same policy version, release window, and bounded incident evidence.",
        " Evidence ledger {record}: audit retention check confirms this corroborating record adds context only and does not alter the decision.",
    )
    record = 1
    while len(prompt.split()) < target:
        prompt += record_templates[(record - 1) % len(record_templates)].format(
            record=record
        )
        record += 1
    return prompt


def _normalized_decision(value: object) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(value, dict):
        return None, "invalid_schema"
    required = {"severity", "release_decision", "escalation_owner", "reason_codes"}
    if set(value) != required or not isinstance(value.get("reason_codes"), list):
        return None, "invalid_schema"
    try:
        normalized = {
            "severity": str(value["severity"]).upper(),
            "release_decision": str(value["release_decision"]).upper(),
            "escalation_owner": str(value["escalation_owner"]).upper(),
            "reason_codes": sorted(str(item).upper() for item in value["reason_codes"]),
        }
    except (TypeError, ValueError):
        return None, "invalid_schema"
    if (
        normalized["severity"] not in {"SEV1", "SEV2", "SEV3"}
        or normalized["release_decision"] not in {"BLOCK", "APPROVE_WITH_MONITORING", "APPROVE"}
        or normalized["escalation_owner"] not in {"DATA_ENGINEERING", "DATA_GOVERNANCE", "SECURITY"}
        or not normalized["reason_codes"]
    ):
        return None, "invalid_schema"
    return normalized, None


def score_governed_release_decision(output: str, target: str) -> tuple[bool, str | None]:
    """Pure semantic JSON decision comparison used by the Inspect scorer and tests."""
    try:
        observed_raw = json.loads(output)
    except json.JSONDecodeError:
        return False, "invalid_json"
    try:
        expected_raw = json.loads(target)
    except json.JSONDecodeError:  # pragma: no cover - repository fixture invariant
        return False, "invalid_target"
    observed, failure = _normalized_decision(observed_raw)
    expected, _ = _normalized_decision(expected_raw)
    if failure is not None:
        return False, failure
    return (observed == expected, None if observed == expected else "incorrect_decision")


@scorer(metrics=[accuracy(), stderr()])
def governed_release_decision() -> object:
    """Score valid governed JSON semantically without an LLM judge."""
    async def score(state: TaskState, target: Target) -> Score:
        passed, failure_category = score_governed_release_decision(
            state.output.completion, target.text
        )
        return Score(
            value=CORRECT if passed else INCORRECT,
            answer=None,
            explanation="governed_release_decision/v1",
            metadata={"failure_category": failure_category},
        )

    return score


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


@solver
def incident_planner_executor_generate(
    plan_schema_version: str = SCAFFOLD_PLAN_SCHEMA_VERSION,
    prompt_version: str = _INCIDENT_PLAN_PROMPT_VERSION,
    executor_context_policy: str = "retained",
) -> Solver:
    """Two-call planner–executor for the prompt-length incident sweep.

    ``retained`` is a declared contract, not an inference: the underlying
    solver appends the executor message to the existing task state after the
    planning call, so the executor receives the original task and the prior
    planning conversation.
    """
    if prompt_version != _INCIDENT_PLAN_PROMPT_VERSION:
        raise ValueError("Unsupported incident planner prompt version.")
    if executor_context_policy != "retained":
        raise ValueError("The incident planner–executor requires retained context.")
    return planner_executor_generate(plan_schema_version)


@task
def incident_prompt_length_sweep() -> Task:
    """48 deterministic enterprise incident prompts across six context bands."""
    samples: list[Sample] = []
    for scenario_id, severity, decision, owner, reasons, summary in _INCIDENTS:
        target = _decision_target(severity, decision, owner, reasons)
        target_digest = f"sha256:{hashlib.sha256(target.encode()).hexdigest()}"
        for length_band in _INCIDENT_LENGTH_BANDS:
            prompt = _incident_prompt(summary, length_band)
            samples.append(
                Sample(
                    id=f"{scenario_id}:{length_band}",
                    input=prompt,
                    target=target,
                    metadata={
                        "scenario_id": scenario_id,
                        "length_band": length_band,
                        "original_prompt_characters": len(prompt),
                        "original_prompt_words": len(prompt.split()),
                        "original_prompt_tokens": len(prompt.split()),
                        "tokenizer": _INCIDENT_TOKENIZER,
                        "token_count_kind": "estimated",
                        "expected_decision_digest": target_digest,
                    },
                )
            )
    return Task(
        dataset=samples,
        solver=generate(),
        scorer=governed_release_decision(),
        name="ai_governance_incident_prompt_length_sweep",
        version=1,
        metadata={
            "task_version": "incident-prompt-length-sweep-v4",
            "sample_count": len(samples),
            "base_incident_count": len(_INCIDENTS),
            "length_bands": list(_INCIDENT_LENGTH_BANDS),
            "tokenizer": _INCIDENT_TOKENIZER,
            "token_count_kind": "estimated",
            "scorer": "governed_release_decision/v1",
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
