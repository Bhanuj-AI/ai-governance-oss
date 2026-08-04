from datetime import UTC, datetime

from kavach.decisions import (
    DecisionEvidenceBuilder,
    DecisionTargetType,
)
from kavach.ontology import (
    EntityType,
    GraphEntity,
    GraphSubgraph,
    InMemoryOntologyGraphQueryRepository,
    InMemoryOntologyGraphRepository,
    OntologyEntity,
    OntologyGraphQueryService,
    OntologyRelationship,
    RelationshipType,
)


def test_build_evidence_graph_for_candidate_with_evaluation_result_and_metrics() -> None:
    repository = _repository_with_candidate_evaluation()
    builder = _builder(repository)

    graph = builder.build_for_target(
        DecisionTargetType.CANDIDATE,
        "candidate-1",
    )

    assert [node.entity_id for node in graph.nodes] == [
        "candidate-1",
        "eval-result-1",
        "eval-run-1",
        "metric-answer-relevance",
        "metric-groundedness",
        "policy-quality-gate",
    ]
    assert {edge.relationship_type for edge in graph.edges} >= {
        RelationshipType.EXECUTES.value,
        RelationshipType.PRODUCES.value,
        RelationshipType.HAS_METRIC.value,
        RelationshipType.GOVERNED_BY.value,
    }
    assert not graph.missing


def test_build_evidence_graph_for_target_with_drift_analysis() -> None:
    repository = _repository_with_candidate_evaluation()
    repository.save_entity(
        _entity(
            EntityType.EVALUATION_COMPARISON.value,
            "comparison-1",
        )
    )
    repository.save_entity(
        _entity(
            EntityType.DRIFT_ANALYSIS.value,
            "drift-1",
            immutable_attributes={"severity": "LOW"},
        )
    )
    repository.save_relationship(
        _relationship(
            "rel-compared-with",
            RelationshipType.COMPARED_WITH.value,
            EntityType.EVALUATION_RESULT.value,
            "eval-result-1",
            EntityType.EVALUATION_COMPARISON.value,
            "comparison-1",
        )
    )
    repository.save_relationship(
        _relationship(
            "rel-caused-drift",
            RelationshipType.CAUSED_DRIFT.value,
            EntityType.EVALUATION_COMPARISON.value,
            "comparison-1",
            EntityType.DRIFT_ANALYSIS.value,
            "drift-1",
        )
    )

    graph = _builder(repository).build_for_target(
        DecisionTargetType.CANDIDATE,
        "candidate-1",
        depth=4,
    )

    assert "drift-1" in {node.entity_id for node in graph.nodes}


def test_build_evidence_graph_with_mcp_audit_evidence() -> None:
    repository = _repository_with_candidate_evaluation()
    repository.save_entity(
        _entity(
            EntityType.MCP_AUDIT_RECORD.value,
            "audit-1",
            immutable_attributes={"status": "SUCCEEDED"},
        )
    )
    repository.save_relationship(
        _relationship(
            "rel-audit",
            RelationshipType.REFERENCES_RESOURCE.value,
            EntityType.MCP_AUDIT_RECORD.value,
            "audit-1",
            EntityType.CANDIDATE.value,
            "candidate-1",
        )
    )

    graph = _builder(repository).build_for_target(
        DecisionTargetType.CANDIDATE,
        "candidate-1",
    )

    assert "audit-1" in {node.entity_id for node in graph.nodes}


def test_missing_target_produces_critical_missing_evidence() -> None:
    graph = _builder(InMemoryOntologyGraphRepository()).build_for_target(
        DecisionTargetType.CANDIDATE,
        "missing-candidate",
    )

    assert graph.nodes == ()
    assert graph.missing[0].severity == "CRITICAL"
    assert graph.missing[0].evidence_type == "Target"


def test_missing_metrics_produces_warning_missing_evidence() -> None:
    repository = InMemoryOntologyGraphRepository()
    repository.save_entity(_entity(EntityType.CANDIDATE.value, "candidate-1"))
    repository.save_entity(
        _entity(EntityType.EVALUATION_RESULT.value, "eval-result-1")
    )
    repository.save_relationship(
        _relationship(
            "rel-generated",
            RelationshipType.GENERATED_FROM.value,
            EntityType.EVALUATION_RESULT.value,
            "eval-result-1",
            EntityType.CANDIDATE.value,
            "candidate-1",
        )
    )

    graph = _builder(repository).build_for_target(
        DecisionTargetType.CANDIDATE,
        "candidate-1",
    )

    assert ("Metric", "WARNING") in {
        (missing.evidence_type, missing.severity) for missing in graph.missing
    }


def test_evidence_summary_extracts_ids() -> None:
    repository = _repository_with_candidate_evaluation()
    repository.save_entity(
        _entity(
            EntityType.DRIFT_ANALYSIS.value,
            "drift-1",
            immutable_attributes={"severity": "LOW"},
        )
    )
    repository.save_relationship(
        _relationship(
            "rel-drift",
            RelationshipType.CAUSED_DRIFT.value,
            EntityType.EVALUATION_RESULT.value,
            "eval-result-1",
            EntityType.DRIFT_ANALYSIS.value,
            "drift-1",
        )
    )

    summary = _builder(repository).summarize(
        _builder(repository).build_for_target(
            DecisionTargetType.CANDIDATE,
            "candidate-1",
        )
    )

    assert summary.evaluation_result_ids == ("eval-result-1",)
    assert summary.metric_ids == (
        "metric-answer-relevance",
        "metric-groundedness",
    )
    assert summary.drift_analysis_ids == ("drift-1",)
    assert summary.policy_ids == ("policy-quality-gate",)


def test_policy_context_maps_metric_scores_and_drift_severity() -> None:
    repository = _repository_with_candidate_evaluation()
    repository.save_entity(
        _entity(
            EntityType.DRIFT_ANALYSIS.value,
            "drift-1",
            immutable_attributes={"severity": "LOW"},
        )
    )
    repository.save_relationship(
        _relationship(
            "rel-drift",
            RelationshipType.CAUSED_DRIFT.value,
            EntityType.EVALUATION_RESULT.value,
            "eval-result-1",
            EntityType.DRIFT_ANALYSIS.value,
            "drift-1",
        )
    )
    builder = _builder(repository)

    context = builder.build_policy_context(
        builder.build_for_target(
            DecisionTargetType.CANDIDATE,
            "candidate-1",
            depth=4,
        )
    )

    assert context.evidence["metrics"]["groundedness"]["score"] == 0.91
    assert context.evidence["metrics"]["answer_relevance"]["score"] == 0.87
    assert context.evidence["drift"]["severity"] == "LOW"


def test_policy_context_maps_job_and_audit_latest_status() -> None:
    repository = _repository_with_candidate_evaluation()
    repository.save_entity(
        _entity(
            EntityType.JOB.value,
            "job-1",
            mutable_attributes={"status": "SUCCEEDED"},
        )
    )
    repository.save_entity(
        _entity(
            EntityType.MCP_AUDIT_RECORD.value,
            "audit-1",
            immutable_attributes={"status": "SUCCEEDED"},
        )
    )
    repository.save_relationship(
        _relationship(
            "rel-job",
            RelationshipType.RESULTED_IN.value,
            EntityType.JOB.value,
            "job-1",
            EntityType.EVALUATION_RESULT.value,
            "eval-result-1",
        )
    )
    repository.save_relationship(
        _relationship(
            "rel-audit",
            RelationshipType.AUDITED_BY.value,
            EntityType.JOB.value,
            "job-1",
            EntityType.MCP_AUDIT_RECORD.value,
            "audit-1",
        )
    )
    builder = _builder(repository)

    context = builder.build_policy_context(
        builder.build_for_target(
            DecisionTargetType.CANDIDATE,
            "candidate-1",
            depth=4,
        )
    )

    assert context.evidence["jobs"]["latest_status"] == "SUCCEEDED"
    assert context.evidence["audit"]["latest_status"] == "SUCCEEDED"


def test_deterministic_ordering_of_nodes_and_edges() -> None:
    graph = _builder(_repository_with_candidate_evaluation()).build_for_target(
        DecisionTargetType.CANDIDATE,
        "candidate-1",
    )

    assert list(graph.nodes) == sorted(
        graph.nodes,
        key=lambda node: (node.entity_type, node.entity_id),
    )
    assert list(graph.edges) == sorted(
        graph.edges,
        key=lambda edge: (
            edge.relationship_type,
            edge.source_type,
            edge.source_id,
            edge.target_type,
            edge.target_id,
        ),
    )


def test_depth_limit_is_passed_to_graph_query_layer() -> None:
    service = RecordingGraphQueryService()
    builder = DecisionEvidenceBuilder(service)

    builder.build_for_target(
        DecisionTargetType.CANDIDATE,
        "candidate-1",
        depth=2,
    )

    assert service.depths == [2]


def test_builder_does_not_mutate_graph_state() -> None:
    repository = _repository_with_candidate_evaluation()
    entity_count = len(repository._entities)
    relationship_count = len(repository._relationships)

    _builder(repository).build_for_target(
        DecisionTargetType.CANDIDATE,
        "candidate-1",
    )

    assert len(repository._entities) == entity_count
    assert len(repository._relationships) == relationship_count


class RecordingGraphQueryService:
    def __init__(self) -> None:
        self.depths: list[int] = []

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> GraphEntity | None:
        return GraphEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            lifecycle="ACTIVE",
            owner="owner",
            ontology_version="1.0.0",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        )

    def get_neighbourhood(
        self,
        entity_type: str,
        entity_id: str,
        *,
        depth: int,
        relationship_types: tuple[str, ...],
        entity_types: tuple[str, ...],
        limit: int,
    ) -> GraphSubgraph:
        self.depths.append(depth)
        return GraphSubgraph()


def _builder(
    repository: InMemoryOntologyGraphRepository,
) -> DecisionEvidenceBuilder:
    return DecisionEvidenceBuilder(
        OntologyGraphQueryService(
            InMemoryOntologyGraphQueryRepository(repository)
        )
    )


def _repository_with_candidate_evaluation() -> InMemoryOntologyGraphRepository:
    repository = InMemoryOntologyGraphRepository()
    for entity in (
        _entity(EntityType.CANDIDATE.value, "candidate-1"),
        _entity(EntityType.EVALUATION_RUN.value, "eval-run-1"),
        _entity(EntityType.EVALUATION_RESULT.value, "eval-result-1"),
        _entity(
            EntityType.METRIC.value,
            "metric-groundedness",
            immutable_attributes={
                "metric_name": "groundedness",
                "score": 0.91,
            },
        ),
        _entity(
            EntityType.METRIC.value,
            "metric-answer-relevance",
            immutable_attributes={
                "metric_name": "answer relevance",
                "score": 0.87,
            },
        ),
        _entity(EntityType.POLICY.value, "policy-quality-gate"),
    ):
        repository.save_entity(entity)
    for relationship in (
        _relationship(
            "rel-executes",
            RelationshipType.EXECUTES.value,
            EntityType.EVALUATION_RUN.value,
            "eval-run-1",
            EntityType.CANDIDATE.value,
            "candidate-1",
        ),
        _relationship(
            "rel-produces",
            RelationshipType.PRODUCES.value,
            EntityType.EVALUATION_RUN.value,
            "eval-run-1",
            EntityType.EVALUATION_RESULT.value,
            "eval-result-1",
        ),
        _relationship(
            "rel-groundedness",
            RelationshipType.HAS_METRIC.value,
            EntityType.EVALUATION_RESULT.value,
            "eval-result-1",
            EntityType.METRIC.value,
            "metric-groundedness",
        ),
        _relationship(
            "rel-answer-relevance",
            RelationshipType.HAS_METRIC.value,
            EntityType.EVALUATION_RESULT.value,
            "eval-result-1",
            EntityType.METRIC.value,
            "metric-answer-relevance",
        ),
        _relationship(
            "rel-policy",
            RelationshipType.GOVERNED_BY.value,
            EntityType.CANDIDATE.value,
            "candidate-1",
            EntityType.POLICY.value,
            "policy-quality-gate",
        ),
    ):
        repository.save_relationship(relationship)
    return repository


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    immutable_attributes: dict[str, object] | None = None,
    mutable_attributes: dict[str, object] | None = None,
) -> OntologyEntity:
    return OntologyEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        owner="owner",
        lifecycle="ACTIVE",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
        immutable_attributes=immutable_attributes or {},
        mutable_attributes=mutable_attributes or {},
        metadata={},
    )


def _relationship(
    relationship_id: str,
    relationship_type: str,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
) -> OntologyRelationship:
    return OntologyRelationship(
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        source_entity_type=source_type,
        source_entity_id=source_id,
        target_entity_type=target_type,
        target_entity_id=target_id,
        created_by="owner",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
