from __future__ import annotations

from kavach.api.models.replay import (
    ReplayAuditRecordResponse,
    ReplayConfigurationResponse,
    ReplayFailureResponse,
    ReplayResponse,
    ReplayResultResponse,
)
from kavach.domain.replay import Replay, ReplayConfiguration
from kavach.providers.provider_descriptor import scrub_sensitive_metadata


class ReplayApiMapper:
    @staticmethod
    def to_audit_record_response(record) -> ReplayAuditRecordResponse:
        return ReplayAuditRecordResponse(
            event_id=record.event_id,
            operation_type=record.operation_type,
            status=record.status,
            occurred_at=record.occurred_at,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            detail=record.detail,
            job_id=record.job_id,
            result_reference=record.result_reference,
        )

    @staticmethod
    def to_configuration_response(
        configuration: ReplayConfiguration,
    ) -> ReplayConfigurationResponse:
        return ReplayConfigurationResponse(
            workflow_id=configuration.workflow_id,
            workflow_version=configuration.workflow_version,
            execution_adapter=configuration.execution_adapter,
            input_snapshot_ref=configuration.input_snapshot_ref,
            state_snapshot_ref=configuration.state_snapshot_ref,
            artifact_refs=list(configuration.artifact_refs),
            prompt_refs=list(configuration.prompt_refs),
            model_refs=list(configuration.model_refs),
            dataset_refs=list(configuration.dataset_refs),
            policy_refs=list(configuration.policy_refs),
            runtime_parameters=scrub_sensitive_metadata(
                dict(configuration.runtime_parameters)
            ),
            configuration_source=configuration.configuration_source.value,
            resolved_at=configuration.resolved_at,
            configuration_hash=configuration.configuration_hash,
        )

    @staticmethod
    def to_response(replay: Replay) -> ReplayResponse:
        configuration = replay.configuration
        failure = replay.failure
        return ReplayResponse(
            replay_id=replay.replay_id,
            source_execution_id=replay.source_execution_id,
            status=replay.status.value,
            mode=replay.mode.value,
            configuration=(
                ReplayApiMapper.to_configuration_response(configuration)
                if configuration
                else None
            ),
            requested_by=replay.requested_by,
            organization_id=replay.organization_id,
            project_id=replay.project_id,
            created_at=replay.created_at,
            updated_at=replay.updated_at,
            archived_at=replay.archived_at,
            failure=(
                ReplayFailureResponse(
                    code=failure.code,
                    message=failure.message,
                    stage=failure.stage.value,
                    details=scrub_sensitive_metadata(dict(failure.details)),
                    occurred_at=failure.occurred_at,
                )
                if failure
                else None
            ),
            metadata=scrub_sensitive_metadata(dict(replay.metadata)),
            job_id=replay.job_id,
            replay_execution_id=replay.replay_execution_id,
            queued_at=replay.queued_at,
            started_at=replay.started_at,
            execution_completed_at=replay.execution_completed_at,
            cancel_requested_at=replay.cancel_requested_at,
            cancelled_at=replay.cancelled_at,
            attempt_count=replay.attempt_count,
            evaluation_job_id=replay.evaluation_job_id,
            baseline_evaluation_id=replay.baseline_evaluation_id,
            replay_evaluation_id=replay.replay_evaluation_id,
            comparison_id=replay.comparison_id,
            drift_id=replay.drift_id,
            result_id=replay.result_id,
            evaluation_started_at=replay.evaluation_started_at,
            evaluation_completed_at=replay.evaluation_completed_at,
            comparison_started_at=replay.comparison_started_at,
            comparison_completed_at=replay.comparison_completed_at,
            completed_at=replay.completed_at,
        )

    @staticmethod
    def to_result_response(result) -> ReplayResultResponse:
        return ReplayResultResponse(
            result_id=result.result_id, replay_id=result.replay_id,
            source_execution_id=result.source_execution_id,
            replay_execution_id=result.replay_execution_id,
            baseline_evaluation_id=result.baseline_evaluation_id,
            replay_evaluation_id=result.replay_evaluation_id,
            comparison_id=result.comparison_id, drift_id=result.drift_id,
            baseline_strategy=result.baseline_strategy,
            comparison_summary=result.comparison_summary.__dict__,
            drift_summary={
                "severity": result.drift_summary.severity,
                "changed_metrics": list(result.drift_summary.changed_metrics),
                "new_metrics": list(result.drift_summary.new_metrics),
                "removed_metrics": list(result.drift_summary.removed_metrics),
                "analyzer_version": result.drift_summary.analyzer_version,
                "threshold_policy": dict(result.drift_summary.threshold_policy),
            },
            created_at=result.created_at,
            metadata=scrub_sensitive_metadata(dict(result.metadata)),
        )
