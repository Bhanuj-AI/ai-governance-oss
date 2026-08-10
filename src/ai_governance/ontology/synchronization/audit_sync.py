from __future__ import annotations

from ai_governance.mcp.audit import MCPExecutionAuditRecord
from ai_governance.ontology import EntityType, OntologyService, RelationshipType
from ai_governance.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    sync_actor,
    sync_relationship,
)


class MCPAuditOntologySynchronizer(BaseOntologySynchronizer[MCPExecutionAuditRecord]):
    """
    Synchronizes MCP write audit records into the ontology projection.
    """

    def __init__(self, ontology_service: OntologyService) -> None:
        super().__init__(
            ontology_service,
            source_name="mcp_audit_plane",
        )

    def _synchronize(
        self,
        entity: MCPExecutionAuditRecord,
    ) -> SynchronizationResult:
        actor_id = sync_actor(
            self._ontology_service,
            entity.actor_id,
            actor_type=entity.actor_type,
        )
        self._ontology_service.create_entity(
            entity_id=entity.audit_id,
            entity_type=EntityType.MCP_AUDIT_RECORD,
            owner=entity.actor_id,
            lifecycle=entity.status,
            created_at=entity.started_at,
            immutable_attributes={
                "audit_id": entity.audit_id,
                "request_id": entity.request_id,
                "correlation_id": entity.correlation_id,
                "tool_name": entity.tool_name,
                "tool_version": entity.tool_version,
                "actor_id": entity.actor_id,
                "actor_type": entity.actor_type,
                "agent_name": entity.agent_name,
                "agent_session_id": entity.agent_session_id,
                "client_name": entity.client_name,
                "client_version": entity.client_version,
                "idempotency_key": entity.idempotency_key,
                "operation_type": entity.operation_type,
                "resource_type": entity.resource_type,
                "request_hash": entity.request_hash,
                "request_summary": entity.request_summary,
                "resolved_versions": entity.resolved_versions,
                "reason": entity.reason,
                "dry_run": entity.dry_run,
            },
            mutable_attributes={
                "status": entity.status,
                "resource_id": entity.resource_id,
                "job_id": entity.job_id,
                "result_reference": entity.result_reference,
                "error_code": entity.error_code,
                "error_message": entity.error_message,
                "completed_at": (
                    entity.completed_at.isoformat()
                    if entity.completed_at is not None
                    else None
                ),
                "duration_ms": entity.duration_ms,
            },
            metadata={
                **entity.metadata,
                "synchronized_from": "mcp_audit_plane",
            },
        )

        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.MCP_AUDIT_RECORD,
                source_id=entity.audit_id,
                relationship_type=RelationshipType.CREATED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.actor_id,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.MCP_AUDIT_RECORD,
                source_id=entity.audit_id,
                relationship_type=RelationshipType.OWNED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.actor_id,
            ),
        ]

        for target in self._resource_targets(entity):
            target_type, target_id = target
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.MCP_AUDIT_RECORD,
                    source_id=entity.audit_id,
                    relationship_type=RelationshipType.REFERENCES_RESOURCE,
                    target_type=target_type,
                    target_id=target_id,
                    created_by=entity.actor_id,
                )
            )
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=target_type,
                    source_id=target_id,
                    relationship_type=RelationshipType.AUDITED_BY,
                    target_type=EntityType.MCP_AUDIT_RECORD,
                    target_id=entity.audit_id,
                    created_by=entity.actor_id,
                )
            )

        if entity.job_id and self._ontology_service.get_entity(
            EntityType.JOB.value,
            entity.job_id,
        ):
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.JOB,
                    source_id=entity.job_id,
                    relationship_type=RelationshipType.AUDITED_BY,
                    target_type=EntityType.MCP_AUDIT_RECORD,
                    target_id=entity.audit_id,
                    created_by=entity.actor_id,
                )
            )

        return SynchronizationResult(
            synchronized_entity_ids=(entity.audit_id, actor_id),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=2,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(
        self,
        entity: MCPExecutionAuditRecord,
    ) -> tuple[str, str]:
        return EntityType.MCP_AUDIT_RECORD.value, entity.audit_id

    def _resource_targets(
        self,
        entity: MCPExecutionAuditRecord,
    ) -> list[tuple[str, str]]:
        target = _resource_target(entity.resource_type, entity.resource_id)
        if target is None:
            return []
        target_type, target_id = target
        if self._ontology_service.get_entity(target_type, target_id) is None:
            return []
        return [target]


def _resource_target(
    resource_type: str,
    resource_id: str | None,
) -> tuple[str, str] | None:
    if resource_id is None:
        return None
    mapping = {
        "job": EntityType.JOB.value,
        "experiment": EntityType.EXPERIMENT.value,
        "experiment_candidate": EntityType.CANDIDATE.value,
        "candidate": EntityType.CANDIDATE.value,
        "evaluation": EntityType.EVALUATION_RESULT.value,
        "evaluation_run": EntityType.EVALUATION_RUN.value,
        "prompt": EntityType.PROMPT_VERSION.value,
        "model": EntityType.MODEL_VERSION.value,
        "dataset": EntityType.DATASET_VERSION.value,
    }
    entity_type = mapping.get(resource_type)
    if entity_type is None:
        return None
    return entity_type, resource_id
