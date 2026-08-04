from __future__ import annotations

from typing import Protocol

from kavach.domain.jobs import Job, JobResult, JobStatus, JobType


class JobHandler(Protocol):
    """
    Handler contract for executing a submitted governance job.
    """

    def handle(
        self,
        job: Job,
    ) -> JobResult:
        ...


class JobExecutor:
    """
    Dispatches governance jobs to registered handlers by job type.
    """

    def __init__(
        self,
        handlers: dict[JobType, JobHandler] | None = None,
    ) -> None:
        self._handlers = dict(handlers or {})

    def execute(
        self,
        job: Job,
    ) -> JobResult:
        """
        Execute one job with its registered job handler.
        """
        handler = self._handlers.get(job.job_type)
        if handler is None:
            operation = _extension_operation(job) if job.job_type is JobType.EXTENSION else None
            handler = _EXTENSION_HANDLERS.get((job.job_type, operation))
        if handler is None:
            return JobResult(
                job_id=job.job_id,
                status=JobStatus.FAILED,
                result_ref=None,
                failure_reason=(
                    f"No job handler registered for '{job.job_type.value}'."
                ),
            )

        return handler.handle(job)


def _extension_operation(job: Job) -> str | None:
    envelope = job.input_refs.get("_kavach_extension")
    if not isinstance(envelope, dict):
        return None
    operation = envelope.get("operation")
    return operation if isinstance(operation, str) and operation.strip() else None

_EXTENSION_HANDLERS: dict[tuple[JobType, str | None], JobHandler] = {}

def register_extension_handlers(definitions) -> None:
    """Install validated plugin handlers used by every subsequently built executor."""
    for definition in definitions:
        if not isinstance(definition.job_type, JobType) or not hasattr(definition.handler, "handle"):
            raise TypeError("Plugin job handlers require a JobType and handle(job) method.")
        operation = getattr(definition, "operation", None)
        if definition.job_type is JobType.EXTENSION and not isinstance(operation, str):
            raise TypeError("Extension jobs require a non-empty operation name.")
        if operation is not None and (not isinstance(operation, str) or not operation.strip()):
            raise TypeError("Job handler operation must be a non-empty string.")
        key = (definition.job_type, operation)
        if key in _EXTENSION_HANDLERS:
            suffix = f"/{operation}" if operation else ""
            raise ValueError(f"Job handler for '{definition.job_type.value}{suffix}' is already registered.")
        _EXTENSION_HANDLERS[key] = definition.handler
