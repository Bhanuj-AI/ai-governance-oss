from datetime import UTC, datetime

from ai_governance.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
    Leaderboard,
    LeaderboardEntry,
)
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.ontology import (
    EntityType,
    InMemoryOntologyGraphRepository,
    OntologyService,
    RelationshipType,
)
from ai_governance.ontology.synchronization import (
    CandidateOntologySynchronizer,
    EvaluationResultOntologySynchronizer,
    EvaluationRunOntologySynchronizer,
    ExperimentOntologySynchronizer,
    LeaderboardOntologySynchronizer,
    PromptOntologySynchronizer,
)


def test_candidate_synchronization_projects_asset_relationships() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    PromptOntologySynchronizer(service).synchronize(
        Prompt(
            prompt_id="prompt-1",
            name="support",
            version="v1",
            template="Hello",
            variables=(),
            created_at=datetime(2026, 6, 30, tzinfo=UTC),
            created_by="owner",
            status=PromptStatus.ACTIVE,
        )
    )
    service.create_entity(
        entity_id="model-1",
        entity_type=EntityType.MODEL_VERSION,
        owner="owner",
        lifecycle="ACTIVE",
    )
    service.create_entity(
        entity_id="dataset-1",
        entity_type=EntityType.DATASET_VERSION,
        owner="owner",
        lifecycle="ACTIVE",
    )
    ExperimentOntologySynchronizer(service).synchronize(
        Experiment(
            experiment_id="experiment-1",
            name="Experiment",
            description="test",
            owner="owner",
            created_at=datetime(2026, 6, 30, tzinfo=UTC),
            status=ExperimentStatus.DRAFT,
        )
    )
    candidate = ExperimentCandidate(
        candidate_id="candidate-1",
        experiment_id="experiment-1",
        name="Candidate",
        prompt_id="prompt-1",
        prompt_version="v1",
        model_id="model-1",
        model_version="v1",
        dataset_id="dataset-1",
        dataset_version="v1",
        evaluation_provider="mock",
        temperature=0,
        top_p=1,
        max_tokens=128,
        metadata={},
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
    )

    result = CandidateOntologySynchronizer(service).synchronize(candidate)

    assert result.succeeded is True
    outgoing = service.find_relationships(
        "Candidate",
        "candidate-1",
        direction="outgoing",
    )
    assert {
        relationship.relationship_type for relationship in outgoing
    } >= {
        RelationshipType.USES.value,
        RelationshipType.PARTICIPATES_IN.value,
        RelationshipType.EVALUATED_BY.value,
    }


def test_evaluation_result_and_run_synchronization_projects_evidence() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    service.create_entity(
        entity_id="candidate-1",
        entity_type=EntityType.CANDIDATE,
        owner="experiment-1",
        lifecycle="CREATED",
    )
    result = EvaluationResult(
        evaluation_id="eval-1",
        execution_id="exec-1",
        evaluator_type="mock",
        evaluator_version="1.0",
        metrics=[EvaluationMetric("quality", 0.91, "good")],
        artifacts=[
            EvaluationArtifact(
                artifact_type="trace",
                uri="file://trace.json",
            )
        ],
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
    )
    run = EvaluationRun(
        run_id="run-1",
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        dataset_version="v1",
        evaluation_provider="mock",
        evaluation_result_id="eval-1",
        started_at=datetime(2026, 6, 30, tzinfo=UTC),
        completed_at=datetime(2026, 6, 30, tzinfo=UTC),
        status=EvaluationRunStatus.COMPLETED,
    )

    result_sync = EvaluationResultOntologySynchronizer(service).synchronize(
        result
    )
    run_sync = EvaluationRunOntologySynchronizer(service).synchronize(run)

    assert result_sync.succeeded is True
    assert run_sync.succeeded is True
    assert service.get_entity("Metric", "metric:eval-1:quality") is not None
    assert service.find_relationships(
        "EvaluationRun",
        "run-1",
        direction="outgoing",
        relationship_type=RelationshipType.PRODUCES.value,
    )


def test_leaderboard_synchronization_projects_ranking_and_recommendation() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    service.create_entity(
        entity_id="candidate-1",
        entity_type=EntityType.CANDIDATE,
        owner="experiment-1",
        lifecycle="CREATED",
    )
    service.create_entity(
        entity_id="run-1",
        entity_type=EntityType.EVALUATION_RUN,
        owner="experiment-1",
        lifecycle="COMPLETED",
    )
    leaderboard = Leaderboard(
        leaderboard_id="leaderboard-1",
        experiment_id="experiment-1",
        ranking_strategy="overall_score",
        generated_at=datetime(2026, 6, 30, tzinfo=UTC),
        entries=(
            LeaderboardEntry(
                rank=1,
                candidate_id="candidate-1",
                overall_score=0.91,
                metrics={"quality": 0.91},
                cost=0.01,
                latency=0.2,
                reason="Ranked by average evaluation metric score.",
            ),
        ),
    )

    result = LeaderboardOntologySynchronizer(service).synchronize(leaderboard)

    assert result.succeeded is True
    assert service.get_entity("Leaderboard", "leaderboard-1") is not None
    assert service.get_entity("LeaderboardEntry", "leaderboard-1-entry-1") is not None
    assert {
        relationship.relationship_type
        for relationship in service.find_relationships(
            "Leaderboard", "leaderboard-1", direction="outgoing"
        )
    } >= {RelationshipType.HAS_ENTRY.value, RelationshipType.RECOMMENDS.value}
