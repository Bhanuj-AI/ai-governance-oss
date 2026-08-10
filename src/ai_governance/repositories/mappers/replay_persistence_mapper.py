from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ai_governance.domain.replay import (
    Replay,
    ReplayConfiguration,
    ReplayConfigurationSource,
    ReplayFailure,
    ReplayFailureStage,
    ReplayMode,
    ReplayStatus,
)


class ReplayPersistenceMapper:
    @staticmethod
    def to_persistence_record(replay: Replay) -> dict[str, Any]:
        return {
            "replay_id": replay.replay_id,
            "source_execution_id": replay.source_execution_id,
            "status": replay.status.value,
            "mode": replay.mode.value,
            "configuration_json": _json(_configuration(replay.configuration)),
            "requested_by": replay.requested_by,
            "organization_id": replay.organization_id,
            "project_id": replay.project_id,
            "request_id": replay.request_id,
            "correlation_id": replay.correlation_id,
            "idempotency_key": replay.idempotency_key,
            "input_hash": replay.input_hash,
            "created_at": replay.created_at.isoformat(),
            "updated_at": replay.updated_at.isoformat(),
            "archived_at": replay.archived_at.isoformat()
            if replay.archived_at
            else None,
            "failure_json": _json(_failure(replay.failure)),
            "metadata_json": _json(dict(replay.metadata)),
            "version": replay.version,
            "job_id": replay.job_id,
            "replay_execution_id": replay.replay_execution_id,
            "queued_at": replay.queued_at.isoformat() if replay.queued_at else None,
            "started_at": replay.started_at.isoformat() if replay.started_at else None,
            "execution_completed_at": (
                replay.execution_completed_at.isoformat()
                if replay.execution_completed_at
                else None
            ),
            "cancel_requested_at": (
                replay.cancel_requested_at.isoformat()
                if replay.cancel_requested_at
                else None
            ),
            "cancelled_at": replay.cancelled_at.isoformat()
            if replay.cancelled_at
            else None,
            "attempt_count": replay.attempt_count,
            "evaluation_job_id": replay.evaluation_job_id,
            "baseline_evaluation_id": replay.baseline_evaluation_id,
            "replay_evaluation_id": replay.replay_evaluation_id,
            "comparison_id": replay.comparison_id,
            "drift_id": replay.drift_id,
            "result_id": replay.result_id,
            "evaluation_started_at": _iso(replay.evaluation_started_at),
            "evaluation_completed_at": _iso(replay.evaluation_completed_at),
            "comparison_started_at": _iso(replay.comparison_started_at),
            "comparison_completed_at": _iso(replay.comparison_completed_at),
            "completed_at": _iso(replay.completed_at),
        }

    @classmethod
    def from_persistence_record(cls, record: Mapping[str, Any]) -> Replay:
        configuration = _configuration_from_json(_value(record, "configuration_json"))
        failure = _failure_from_json(_value(record, "failure_json"))
        return Replay(
            replay_id=str(record["replay_id"]),
            source_execution_id=str(record["source_execution_id"]),
            status=ReplayStatus(str(record["status"])),
            mode=ReplayMode(str(record["mode"])),
            configuration=configuration,
            requested_by=str(record["requested_by"]),
            organization_id=str(record["organization_id"]),
            project_id=str(record["project_id"]),
            request_id=str(record["request_id"]),
            correlation_id=_value(record, "correlation_id"),
            idempotency_key=str(record["idempotency_key"]),
            input_hash=str(record["input_hash"]),
            created_at=datetime.fromisoformat(str(record["created_at"])),
            updated_at=datetime.fromisoformat(str(record["updated_at"])),
            archived_at=_datetime_or_none(_value(record, "archived_at")),
            failure=failure,
            metadata=_load_json(_value(record, "metadata_json"), {}),
            version=int(record["version"]),
            job_id=_value(record, "job_id"),
            replay_execution_id=_value(record, "replay_execution_id"),
            queued_at=_datetime_or_none(_value(record, "queued_at")),
            started_at=_datetime_or_none(_value(record, "started_at")),
            execution_completed_at=_datetime_or_none(
                _value(record, "execution_completed_at")
            ),
            cancel_requested_at=_datetime_or_none(
                _value(record, "cancel_requested_at")
            ),
            cancelled_at=_datetime_or_none(_value(record, "cancelled_at")),
            attempt_count=int(_value(record, "attempt_count") or 0),
            evaluation_job_id=_value(record, "evaluation_job_id"),
            baseline_evaluation_id=_value(record, "baseline_evaluation_id"),
            replay_evaluation_id=_value(record, "replay_evaluation_id"),
            comparison_id=_value(record, "comparison_id"),
            drift_id=_value(record, "drift_id"),
            result_id=_value(record, "result_id"),
            evaluation_started_at=_datetime_or_none(
                _value(record, "evaluation_started_at")
            ),
            evaluation_completed_at=_datetime_or_none(
                _value(record, "evaluation_completed_at")
            ),
            comparison_started_at=_datetime_or_none(
                _value(record, "comparison_started_at")
            ),
            comparison_completed_at=_datetime_or_none(
                _value(record, "comparison_completed_at")
            ),
            completed_at=_datetime_or_none(_value(record, "completed_at")),
        )


def _configuration(configuration: ReplayConfiguration | None) -> dict[str, Any] | None:
    if configuration is None:
        return None
    return {
        "workflow_id": configuration.workflow_id,
        "workflow_version": configuration.workflow_version,
        "execution_adapter": configuration.execution_adapter,
        "input_snapshot_ref": configuration.input_snapshot_ref,
        "state_snapshot_ref": configuration.state_snapshot_ref,
        "artifact_refs": list(configuration.artifact_refs),
        "prompt_refs": list(configuration.prompt_refs),
        "model_refs": list(configuration.model_refs),
        "dataset_refs": list(configuration.dataset_refs),
        "policy_refs": list(configuration.policy_refs),
        "runtime_parameters": dict(configuration.runtime_parameters),
        "configuration_source": configuration.configuration_source.value,
        "resolved_at": configuration.resolved_at.isoformat()
        if configuration.resolved_at
        else None,
        "configuration_hash": configuration.configuration_hash,
    }


def _configuration_from_json(value: object) -> ReplayConfiguration | None:
    data = _load_json(value, None)
    if data is None:
        return None
    return ReplayConfiguration(
        workflow_id=data["workflow_id"],
        workflow_version=data["workflow_version"],
        execution_adapter=data["execution_adapter"],
        input_snapshot_ref=data["input_snapshot_ref"],
        state_snapshot_ref=data["state_snapshot_ref"],
        artifact_refs=tuple(data.get("artifact_refs", ())),
        prompt_refs=tuple(data.get("prompt_refs", ())),
        model_refs=tuple(data.get("model_refs", ())),
        dataset_refs=tuple(data.get("dataset_refs", ())),
        policy_refs=tuple(data.get("policy_refs", ())),
        runtime_parameters=data.get("runtime_parameters", {}),
        configuration_source=ReplayConfigurationSource(data["configuration_source"]),
        resolved_at=_datetime_or_none(data.get("resolved_at")),
        configuration_hash=data["configuration_hash"],
    )


def _failure(failure: ReplayFailure | None) -> dict[str, Any] | None:
    if failure is None:
        return None
    return {
        "code": failure.code,
        "message": failure.message,
        "stage": failure.stage.value,
        "details": dict(failure.details),
        "occurred_at": failure.occurred_at.isoformat(),
    }


def _failure_from_json(value: object) -> ReplayFailure | None:
    data = _load_json(value, None)
    if data is None:
        return None
    return ReplayFailure(
        code=data["code"],
        message=data["message"],
        stage=ReplayFailureStage(data["stage"]),
        details=data.get("details", {}),
        occurred_at=datetime.fromisoformat(data["occurred_at"]),
    )


def _json(value: object) -> str | None:
    return json.dumps(value, sort_keys=True) if value is not None else None


def _load_json(value: object, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(str(value))


def _value(record: Mapping[str, Any], key: str) -> Any:
    try:
        return record[key]
    except (KeyError, IndexError):
        return None


def _datetime_or_none(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
