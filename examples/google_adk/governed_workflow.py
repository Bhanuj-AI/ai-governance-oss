"""Public-API-only evidence adapter for Google ADK workflow nodes.

This module deliberately has no dependency on ``google-adk``.  It receives the
public context object passed to a Google ADK function node and records bounded,
provider-neutral ``WORKFLOW_STEP`` evidence through the Agent Executions REST
API.  Keeping it outside the control-plane package means ADK remains an
optional runtime dependency and no Google-specific domain type enters Core.

The adapter is unidirectional and fail-open: an unavailable governance API
never changes a node's return value, exception, route, or ADK state.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

P = ParamSpec("P")
R = TypeVar("R")

_SOURCE_KIND = "google_adk.node"
_MAX_ATTRIBUTE_LENGTH = 256


class EvidenceTransport(Protocol):
    """Minimal outbound transport boundary, suitable for test fakes."""

    def request(
        self,
        *,
        method: str,
        url: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


class WorkflowStepEvidence(Protocol):
    """Evidence operations needed by a decorated ADK node."""

    def workflow_step_started(self, step: ADKWorkflowStep) -> None: ...

    def workflow_step_completed(self, step: ADKWorkflowStep) -> None: ...

    def workflow_step_failed(self, step: ADKWorkflowStep) -> None: ...

    def complete(self, status: str) -> None: ...


class UrllibEvidenceTransport:
    """Small standard-library JSON transport for a control-plane deployment."""

    def request(
        self,
        *,
        method: str,
        url: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:512]
            raise RuntimeError(
                f"Control-plane request failed with HTTP {exc.code}: {detail}"
            ) from exc

        parsed = json.loads(body) if body else {}
        if not isinstance(parsed, dict):
            raise TypeError("Control-plane response must be a JSON object.")
        return cast(dict[str, Any], parsed)


@dataclass(frozen=True)
class AIGovernanceRuntimeClient:
    """REST client for bounded execution and workflow-step evidence.

    ``headers`` must carry the deployment's ordinary authentication and tenant
    context.  They are supplied by the caller and never logged by this module.
    """

    base_url: str
    headers: Mapping[str, str]
    transport: EvidenceTransport = field(default_factory=UrllibEvidenceTransport)
    timeout_seconds: float = 2.0

    def start_execution(
        self,
        *,
        agent_id: str,
        agent_name: str,
        agent_version: str,
        root_invocation_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> WorkflowStepEvidence:
        """Create or recover the execution, returning a no-op session on delivery failure."""
        try:
            response = self._request(
                "POST",
                "/api/v1/agent-executions",
                {
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "agent_version": agent_version,
                    "external_execution_id": root_invocation_id,
                    "runtime_provider": "google_adk",
                    "correlation_id": root_invocation_id,
                    "metadata": dict(metadata or {}),
                },
            )
            execution = _object_at(response, "execution")
            execution_id = _required_text(execution.get("execution_id"))
            if execution_id is None:
                raise RuntimeError(
                    "Control-plane response did not contain execution.execution_id."
                )
        except Exception:  # noqa: BLE001 - external evidence delivery is fail-open.
            return NoOpADKExecutionEvidence()
        return ADKExecutionEvidence(self, execution_id)

    def _append_workflow_step(
        self,
        execution_id: str,
        step: ADKWorkflowStep,
        lifecycle: str,
    ) -> None:
        payload: dict[str, Any] = {
            "event_type": "WORKFLOW_STEP",
            "step_id": step.step_id,
            "step_name": step.step_name,
            "lifecycle": lifecycle,
            "source_kind": _SOURCE_KIND,
            "attributes": dict(step.attributes),
            "idempotency_key": f"{step.step_id}:{lifecycle}",
        }
        if step.parent_step_id is not None:
            payload["parent_step_id"] = step.parent_step_id
        self._request(
            "POST", f"/api/v1/agent-executions/{execution_id}/events", payload
        )

    def _complete_execution(self, execution_id: str, status: str) -> None:
        self._request(
            "POST",
            f"/api/v1/agent-executions/{execution_id}/complete",
            {"status": status},
        )

    def _request(
        self, method: str, path: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self.transport.request(
            method=method,
            url=f"{self.base_url.rstrip('/')}{path}",
            payload=payload,
            headers=self.headers,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass(frozen=True)
class ADKExecutionEvidence:
    """Evidence session for exactly one already-started ADK root invocation."""

    client: AIGovernanceRuntimeClient
    execution_id: str

    def workflow_step_started(self, step: ADKWorkflowStep) -> None:
        self.client._append_workflow_step(self.execution_id, step, "STARTED")

    def workflow_step_completed(self, step: ADKWorkflowStep) -> None:
        self.client._append_workflow_step(self.execution_id, step, "COMPLETED")

    def workflow_step_failed(self, step: ADKWorkflowStep) -> None:
        self.client._append_workflow_step(self.execution_id, step, "FAILED")

    def complete(self, status: str) -> None:
        """Mark the root execution ``SUCCEEDED``, ``FAILED``, or ``CANCELLED``."""
        if status not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            raise ValueError("status must be SUCCEEDED, FAILED, or CANCELLED.")
        try:
            self.client._complete_execution(self.execution_id, status)
        except Exception:  # noqa: BLE001, S110 - runtime evidence is explicitly fail-open.
            pass


class NoOpADKExecutionEvidence:
    """Fail-open session used when execution-start delivery is unavailable."""

    def workflow_step_started(self, step: ADKWorkflowStep) -> None:
        del step

    def workflow_step_completed(self, step: ADKWorkflowStep) -> None:
        del step

    def workflow_step_failed(self, step: ADKWorkflowStep) -> None:
        del step

    def complete(self, status: str) -> None:
        del status


@dataclass(frozen=True)
class ADKWorkflowStep:
    """Bounded provider facts projected from an ADK public node context."""

    step_id: str
    step_name: str
    parent_step_id: str | None
    attributes: Mapping[str, Any]


def governed_adk_node(
    evidence: WorkflowStepEvidence,
    *,
    step_name: str | None = None,
    context_argument: int = 0,
    context_keyword: str | None = "ctx",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a Google ADK function node with fail-open workflow evidence.

    The ADK public ``Context`` must be the positional argument selected by
    ``context_argument`` (normally zero), or the optional ``context_keyword``
    (``ctx`` by default). A context without the stable public identifiers
    ``invocation_id``, ``run_id``, and ``node_path`` is left uninstrumented
    rather than emitting ambiguous evidence.
    """
    if context_argument < 0:
        raise ValueError("context_argument must be non-negative.")

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def async_wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
                step = _workflow_step_from_context(
                    _context_from_call(
                        args, kwargs, context_argument, context_keyword
                    ),
                    step_name,
                )
                _emit_safely(evidence.workflow_step_started, step)
                try:
                    result = await function(*args, **kwargs)
                except Exception:
                    _emit_safely(evidence.workflow_step_failed, step)
                    raise
                _emit_safely(evidence.workflow_step_completed, step)
                return result

            return cast(Callable[P, R], async_wrapped)

        @wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            step = _workflow_step_from_context(
                _context_from_call(args, kwargs, context_argument, context_keyword),
                step_name,
            )
            _emit_safely(evidence.workflow_step_started, step)
            try:
                result = function(*args, **kwargs)
            except Exception:
                _emit_safely(evidence.workflow_step_failed, step)
                raise
            _emit_safely(evidence.workflow_step_completed, step)
            return result

        return wrapped

    return decorate


def _workflow_step_from_context(context: object, explicit_name: str | None) -> ADKWorkflowStep | None:
    """Read only documented ADK context facts and derive stable step evidence."""
    invocation_id = _required_text(getattr(context, "invocation_id", None))
    run_id = _required_text(getattr(context, "run_id", None))
    node_path = _required_text(getattr(context, "node_path", None))
    if invocation_id is None or run_id is None or node_path is None:
        return None

    parent_context = getattr(context, "parent_ctx", None)
    parent_step_id = _step_id_from_function_node_context(parent_context)
    resolved_name = _required_text(explicit_name) or _node_name(context, node_path)
    if resolved_name is None:
        return None

    attributes: dict[str, Any] = {
        "adk_node_path": _bounded(node_path),
        "adk_run_id": _bounded(run_id),
    }
    attempt_count = getattr(context, "attempt_count", None)
    if isinstance(attempt_count, int) and attempt_count >= 0:
        attributes["adk_attempt_count"] = attempt_count
    return ADKWorkflowStep(
        step_id=_stable_step_id(invocation_id, run_id, node_path),
        step_name=_bounded(resolved_name),
        parent_step_id=parent_step_id,
        attributes=attributes,
    )


def _step_id_from_function_node_context(context: object) -> str | None:
    """Return a parent only when ADK identifies it as a function node.

    A child ``FunctionNode`` normally has the surrounding ``Workflow`` as its
    parent context. The workflow is an ADK orchestration container, not a
    decorated function node, so it has no matching ``WORKFLOW_STEP`` event.
    Sending that derived parent ID makes the control plane correctly reject
    the child event. Restricting linkage to a parent FunctionNode keeps real
    nested function-node relationships while avoiding invented parents.
    """
    node = getattr(context, "node", None)
    if type(node).__name__ != "FunctionNode":
        return None
    invocation_id = _required_text(getattr(context, "invocation_id", None))
    run_id = _required_text(getattr(context, "run_id", None))
    node_path = _required_text(getattr(context, "node_path", None))
    if invocation_id is None or run_id is None or node_path is None:
        return None
    return _stable_step_id(invocation_id, run_id, node_path)


def _stable_step_id(invocation_id: str, run_id: str, node_path: str) -> str:
    """Hash stable public ADK identifiers without exposing them as an ID."""
    digest = hashlib.sha256(
        f"{invocation_id}\x1f{run_id}\x1f{node_path}".encode()
    ).hexdigest()
    return f"adk-step-{digest}"


def _node_name(context: object, node_path: str) -> str | None:
    node = getattr(context, "node", None)
    name = _required_text(getattr(node, "name", None))
    if name is not None:
        return name
    path_parts = [part for part in node_path.replace("/", ".").split(".") if part]
    return path_parts[-1] if path_parts else None


def _context_from_call(
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    context_argument: int,
    context_keyword: str | None,
) -> object:
    if context_argument < len(args):
        return args[context_argument]
    if context_keyword is not None:
        return kwargs.get(context_keyword)
    return None


def _emit_safely(
    emit: Callable[[ADKWorkflowStep], None], step: ADKWorkflowStep | None
) -> None:
    """Evidence transport failures must not change ADK application behavior."""
    if step is None:
        return
    try:
        emit(step)
    except Exception:  # noqa: BLE001, S110 - runtime evidence is explicitly fail-open.
        pass


def _required_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _bounded(value: str) -> str:
    return value[:_MAX_ATTRIBUTE_LENGTH]


def _object_at(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    child = value.get(key)
    if not isinstance(child, Mapping):
        raise TypeError(f"Control-plane response did not contain a JSON object at '{key}'.")
    return child
