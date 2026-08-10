from __future__ import annotations

from typing import Any

from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.clients import RestClient, RestClientError
from ai_governance.mcp.dto import (
    EvaluationSubmitAsyncRequest,
    ExperimentAddCandidateRequest,
    ExperimentCreateRequest,
    ExperimentRunAsyncRequest,
    JobMutationRequest,
    ReplayArchiveToolRequest,
    ReplayCancelToolRequest,
    ReplayCreateToolRequest,
    ReplaySubmitToolRequest,
    ReplayEvaluateToolRequest,
    WriteEnvelope,
)
from ai_governance.mcp.exceptions import map_exception
from ai_governance.mcp.handlers._rest_tool import rest_post
from ai_governance.mcp.observability import MCPMetrics
from ai_governance.mcp.registry import ToolRegistry


def register_write_tools(
    registry: ToolRegistry,
    rest_client: RestClient,
    metrics: MCPMetrics,
    audit_log: MCPExecutionAuditLog,
) -> None:
    registry.register(
        name="replay.create",
        description="Create or dry-run a governed Replay request without executing it.",
        request_model=ReplayCreateToolRequest,
        handler=lambda request: _replay_create_call(
            request, rest_client, metrics, audit_log
        ),
    )
    registry.register(
        name="replay.archive",
        description="Archive a Replay request while preserving governance evidence.",
        request_model=ReplayArchiveToolRequest,
        handler=lambda request: _write_call(
            tool_name="replay.archive",
            operation_type="ARCHIVE_REPLAY",
            resource_type="replay",
            resource_id=request.replay_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            audit_log=audit_log,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                f"/api/v1/replays/{request.replay_id}/archive",
                body={"reason": request.reason},
            ),
        ),
    )
    registry.register(
        name="replay.submit",
        description="Submit a READY Replay through the Job Execution Plane.",
        request_model=ReplaySubmitToolRequest,
        handler=lambda request: _write_call(
            tool_name="replay.submit",
            operation_type="SUBMIT_REPLAY_EXECUTION",
            resource_type="replay",
            resource_id=request.replay_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            audit_log=audit_log,
            validate_dry_run=True,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                f"/api/v1/replays/{request.replay_id}/submit",
                body={"reason": request.reason, "dry_run": request.dry_run},
            ),
        ),
    )
    registry.register(
        name="replay.cancel",
        description="Request cancellation of a submitted Replay execution.",
        request_model=ReplayCancelToolRequest,
        handler=lambda request: _write_call(
            tool_name="replay.cancel",
            operation_type="CANCEL_REPLAY_EXECUTION",
            resource_type="replay",
            resource_id=request.replay_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            audit_log=audit_log,
            validate_dry_run=True,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                f"/api/v1/replays/{request.replay_id}/cancel",
                body={"reason": request.reason, "dry_run": request.dry_run},
            ),
        ),
    )
    registry.register(
        name="replay.evaluate",
        description="Submit or dry-run governed replay evaluation.",
        request_model=ReplayEvaluateToolRequest,
        handler=lambda request: _write_call(
            tool_name="replay.evaluate",
            operation_type="SUBMIT_REPLAY_EVALUATION",
            resource_type="replay",
            resource_id=request.replay_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            audit_log=audit_log,
            validate_dry_run=True,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                f"/api/v1/replays/{request.replay_id}/evaluate",
                body={
                    "reason": request.reason,
                    "dry_run": request.dry_run,
                    "baseline_strategy": request.baseline_strategy,
                    "baseline_evaluation_id": request.baseline_evaluation_id,
                    "evaluation_provider": request.evaluation_provider,
                },
            ),
        ),
    )
    registry.register(
        name="evaluation.submit_async",
        description="Submit an asynchronous evaluation job.",
        request_model=EvaluationSubmitAsyncRequest,
        handler=lambda request: _write_call(
            tool_name="evaluation.submit_async",
            operation_type="SUBMIT_EVALUATION_JOB",
            resource_type="evaluation",
            resource_id=request.execution_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            resolved_versions={
                "provider_name": request.provider_name,
                "workflow_id": request.workflow_id,
            },
            audit_log=audit_log,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                "/api/v1/evaluations/jobs",
                body=_evaluation_job_body(request),
            ),
        ),
    )
    registry.register(
        name="experiment.create",
        description="Submit an asynchronous experiment creation job.",
        request_model=ExperimentCreateRequest,
        handler=lambda request: _write_call(
            tool_name="experiment.create",
            operation_type="CREATE_EXPERIMENT",
            resource_type="experiment",
            resource_id=request.name,
            envelope=request,
            payload=request.model_dump(mode="json"),
            audit_log=audit_log,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                "/api/v1/jobs",
                body=_experiment_create_job_body(request),
            ),
        ),
    )
    registry.register(
        name="experiment.add_candidate",
        description="Submit an asynchronous experiment candidate registration job.",
        request_model=ExperimentAddCandidateRequest,
        handler=lambda request: _write_call(
            tool_name="experiment.add_candidate",
            operation_type="ADD_EXPERIMENT_CANDIDATE",
            resource_type="experiment_candidate",
            resource_id=request.experiment_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            resolved_versions={
                "prompt_version": request.prompt_version,
                "model_version": request.model_version,
                "dataset_version": request.dataset_version,
                "provider_name": request.provider_name,
            },
            audit_log=audit_log,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                "/api/v1/jobs",
                body=_experiment_candidate_job_body(request),
            ),
        ),
    )
    registry.register(
        name="experiment.run_async",
        description="Submit an asynchronous experiment execution job.",
        request_model=ExperimentRunAsyncRequest,
        handler=lambda request: _write_call(
            tool_name="experiment.run_async",
            operation_type="RUN_EXPERIMENT",
            resource_type="experiment",
            resource_id=request.experiment_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            audit_log=audit_log,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                f"/api/v1/experiments/{request.experiment_id}/run",
                body=_experiment_run_async_body(request),
            ),
        ),
    )
    registry.register(
        name="job.cancel",
        description="Cancel a queued or running job.",
        request_model=JobMutationRequest,
        handler=lambda request: _write_call(
            tool_name="job.cancel",
            operation_type="CANCEL_JOB",
            resource_type="job",
            resource_id=request.job_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            audit_log=audit_log,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                f"/api/v1/jobs/{request.job_id}/cancel",
                body=_write_envelope_body(request),
            ),
        ),
    )
    registry.register(
        name="job.retry",
        description="Retry a failed job.",
        request_model=JobMutationRequest,
        handler=lambda request: _write_call(
            tool_name="job.retry",
            operation_type="RETRY_JOB",
            resource_type="job",
            resource_id=request.job_id,
            envelope=request,
            payload=request.model_dump(mode="json"),
            audit_log=audit_log,
            rest_call=lambda: rest_post(
                rest_client,
                metrics,
                f"/api/v1/jobs/{request.job_id}/retry",
                body=_write_envelope_body(request),
            ),
        ),
    )


def _write_call(
    *,
    tool_name: str,
    operation_type: str,
    resource_type: str,
    resource_id: str | None,
    envelope: WriteEnvelope,
    payload: dict[str, Any],
    audit_log: MCPExecutionAuditLog,
    rest_call: Any,
    resolved_versions: dict[str, Any] | None = None,
    validate_dry_run: bool = False,
) -> Any:
    audit_record = audit_log.start(
        tool_name=tool_name,
        operation_type=operation_type,
        resource_type=resource_type,
        resource_id=resource_id,
        envelope=envelope,
        payload=payload,
        resolved_versions=resolved_versions,
    )

    if envelope.dry_run and not validate_dry_run:
        result = {
            "dry_run": True,
            "status": "VALIDATED",
            "request_id": envelope.request_id,
            "correlation_id": envelope.correlation_id or envelope.request_id,
            "operation_type": operation_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        audit_log.complete(audit_record, status="DRY_RUN")
        return result

    try:
        result = rest_call()
        audit_log.complete(
            audit_record,
            status="DRY_RUN" if envelope.dry_run else "SUCCEEDED",
            job_id=_job_id(result),
            result_reference=_result_reference(result),
        )
        return result
    except RestClientError as exc:
        error = map_exception(exc)
        audit_log.complete(
            audit_record,
            status="FAILED",
            error_code=error.code,
            error_message=error.message,
        )
        raise


def _replay_create_call(
    request: ReplayCreateToolRequest,
    rest_client: RestClient,
    metrics: MCPMetrics,
    audit_log: MCPExecutionAuditLog,
) -> Any:
    audit_record = audit_log.start(
        tool_name="replay.create",
        operation_type="CREATE_REPLAY",
        resource_type="replay",
        resource_id=request.source_execution_id,
        envelope=request,
        payload=request.model_dump(mode="json"),
    )
    try:
        result = rest_post(
            rest_client,
            metrics,
            "/api/v1/replays",
            body={
                "source_execution_id": request.source_execution_id,
                "mode": request.mode,
                "configuration_source": request.configuration_source,
                "idempotency_key": request.idempotency_key,
                "metadata": {**request.metadata, "reason": request.reason},
                "reason": request.reason,
                "dry_run": request.dry_run,
            },
        )
        audit_log.complete(
            audit_record,
            status="DRY_RUN" if request.dry_run else "SUCCEEDED",
            result_reference=_result_reference(result),
        )
        return result
    except RestClientError as exc:
        error = map_exception(exc)
        audit_log.complete(
            audit_record,
            status="FAILED",
            error_code=error.code,
            error_message=error.message,
        )
        raise


def _evaluation_job_body(
    request: EvaluationSubmitAsyncRequest,
) -> dict[str, Any]:
    body = request.model_dump(mode="json")
    body["submitted_by"] = request.submitted_by()
    return body


def _experiment_create_job_body(
    request: ExperimentCreateRequest,
) -> dict[str, Any]:
    return _job_body(
        request,
        job_type="EXPERIMENT",
        input_refs={
            "operation": "experiment.create",
            "request_id": request.request_id,
            "correlation_id": request.correlation_id or request.request_id,
            "name": request.name,
            "description": request.description,
            "metadata": request.metadata,
        },
    )


def _experiment_candidate_job_body(
    request: ExperimentAddCandidateRequest,
) -> dict[str, Any]:
    return _job_body(
        request,
        job_type="EXPERIMENT",
        input_refs={
            "operation": "experiment.add_candidate",
            "request_id": request.request_id,
            "correlation_id": request.correlation_id or request.request_id,
            "experiment_id": request.experiment_id,
            "candidate_name": request.candidate_name,
            "prompt_version": request.prompt_version,
            "model_version": request.model_version,
            "dataset_version": request.dataset_version,
            "provider_name": request.provider_name,
            "runtime_parameters": request.runtime_parameters,
            "metadata": request.candidate_metadata,
        },
    )


def _experiment_run_async_body(
    request: ExperimentRunAsyncRequest,
) -> dict[str, Any]:
    body = {
        "metric_specs": request.metric_specs,
        "provider_config": request.provider_config,
        **_write_envelope_body(request),
        "submitted_by": request.submitted_by(),
        "max_attempts": request.max_attempts,
    }
    return body


def _job_body(
    request: WriteEnvelope,
    *,
    job_type: str,
    input_refs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "job_type": job_type,
        "input_refs": input_refs,
        "idempotency_key": request.idempotency_key,
        "submitted_by": request.submitted_by(),
        "max_attempts": request.max_attempts,
    }


def _write_envelope_body(request: WriteEnvelope) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "idempotency_key": request.idempotency_key,
        "requested_by": request.requested_by,
        "actor_type": request.actor_type,
        "reason": request.reason,
        "dry_run": request.dry_run,
        "metadata": request.metadata,
        "correlation_id": request.correlation_id,
        "agent_name": request.agent_name,
        "agent_session_id": request.agent_session_id,
        "client_name": request.client_name,
        "client_version": request.client_version,
    }


def _job_id(result: Any) -> str | None:
    return (
        str(result["job_id"])
        if isinstance(result, dict) and result.get("job_id")
        else None
    )


def _result_reference(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    value = result.get("result_ref") or result.get("result_reference")
    return str(value) if value is not None else None
