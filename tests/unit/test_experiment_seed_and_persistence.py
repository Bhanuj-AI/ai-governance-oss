from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI

from kavach.api.demo_seed import (
    _resolve_graph_query_service,
    seed_demo_experiment_workflows,
    seed_demo_experiments,
    seed_demo_registry_assets,
    synchronize_demo_experiment_graph,
)
from kavach.domain.datasets import Dataset, DatasetStatus
from kavach.api.dependencies import get_ontology_graph_query_repository
from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.experiments import Experiment, ExperimentStatus
from kavach.ontology import (
    EntityType,
    InMemoryOntologyGraphRepository,
    OntologyService,
    RelationshipType,
)
from kavach.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from kavach.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from kavach.repositories.in_memory_evaluation_run_repository import (
    InMemoryEvaluationRunRepository,
)
from kavach.repositories.in_memory_experiment_candidate_repository import (
    InMemoryExperimentCandidateRepository,
)
from kavach.repositories.in_memory_experiment_repository import (
    InMemoryExperimentRepository,
)
from kavach.repositories.in_memory_leaderboard_repository import (
    InMemoryLeaderboardRepository,
)
from kavach.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from kavach.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from kavach.repositories.mappers.experiment_persistence_mapper import (
    ExperimentPersistenceMapper,
)
from kavach.repositories.sqlite.sqlite_experiment_repository import (
    SQLiteExperimentRepository,
)
from kavach.repositories.postgres.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from kavach.repositories.snowflake.snowflake_experiment_repository import (
    SnowflakeExperimentRepository,
)


def _workflow_repositories() -> tuple[object, ...]:
    return (
        InMemoryExperimentRepository(),
        InMemoryExperimentCandidateRepository(),
        InMemoryEvaluationRunRepository(),
        InMemoryEvaluationRepository(),
        InMemoryLeaderboardRepository(),
        InMemoryPromptRepository(),
        InMemoryModelRepository(),
        InMemoryDatasetRepository(),
    )


def test_demo_experiment_inventory_is_tenant_scoped_and_idempotent() -> None:
    repository = InMemoryExperimentRepository()

    seeded = seed_demo_experiments(repository, minimum_count=15)

    assert len(seeded) == 15
    assert len(repository.find_all()) == 15
    assert {item.status for item in repository.find_all()} == {
        ExperimentStatus.COMPLETED,
        ExperimentStatus.RUNNING,
        ExperimentStatus.DRAFT,
        ExperimentStatus.FAILED,
    }
    assert seed_demo_experiments(repository, minimum_count=15) == seeded

    other_tenant_repository = InMemoryExperimentRepository()
    other_tenant_repository.save(
        Experiment(
            experiment_id="demo-experiment-01",
            name="Existing other tenant experiment",
            description="Tenant isolation test",
            owner="owner",
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
            status=ExperimentStatus.DRAFT,
            organization_id="other-org",
            project_id="other-project",
        )
    )

    assert (
        seed_demo_experiments(
            other_tenant_repository,
            organization_id="target-org",
            project_id="target-project",
            minimum_count=1,
        )
        == ()
    )


def test_demo_workflows_seed_evidence_and_are_idempotent() -> None:
    (
        experiment_repository,
        candidate_repository,
        run_repository,
        evaluation_repository,
        leaderboard_repository,
        prompt_repository,
        model_repository,
        dataset_repository,
    ) = _workflow_repositories()
    seed_demo_experiments(experiment_repository, minimum_count=5)
    seed_demo_registry_assets(prompt_repository, model_repository, dataset_repository)

    seed_demo_experiment_workflows(
        experiment_repository,
        candidate_repository,
        run_repository,
        evaluation_repository,
        leaderboard_repository,
    )

    completed_runs = run_repository.find_by_experiment_id("demo-experiment-01")
    failed_runs = run_repository.find_by_experiment_id("demo-experiment-05")
    assert len(completed_runs) == 2
    assert len(failed_runs) == 2
    assert sum(run.status.value == "FAILED" for run in failed_runs) == 1
    assert len(leaderboard_repository.find_by_experiment_id("demo-experiment-01")) == 1
    assert len(leaderboard_repository.find_by_experiment_id("demo-experiment-05")) == 1
    evaluation_ids = [
        f"demo-experiment-{experiment_number:02d}-{variant}-evaluation"
        for experiment_number in (1, 2, 5)
        for variant in ("baseline", "optimized")
    ]
    assert all(
        evaluation_repository.find_by_evaluation_id(evaluation_id) is not None
        for evaluation_id in evaluation_ids
    )

    evaluation_records = tuple(
        evaluation_repository.find_by_evaluation_id(evaluation_id)
        for evaluation_id in evaluation_ids
    )
    counts = (
        len(candidate_repository.find_all()),
        len(run_repository.find_all()),
        evaluation_records,
        len(leaderboard_repository.find_all()),
    )
    seed_demo_experiment_workflows(
        experiment_repository,
        candidate_repository,
        run_repository,
        evaluation_repository,
        leaderboard_repository,
    )
    assert counts == (
        len(candidate_repository.find_all()),
        len(run_repository.find_all()),
        tuple(
            evaluation_repository.find_by_evaluation_id(evaluation_id)
            for evaluation_id in evaluation_ids
        ),
        len(leaderboard_repository.find_all()),
    )


def test_demo_registry_seed_writes_dataset_content_to_configured_object_store(
    monkeypatch,
) -> None:
    class FakeObjectStore:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def put_bytes(self, **kwargs: object) -> None:
            self.calls.append(kwargs)

    prompt_repository = InMemoryPromptRepository()
    model_repository = InMemoryModelRepository()
    dataset_repository = InMemoryDatasetRepository()
    object_store = FakeObjectStore()
    original_created_at = datetime(2026, 7, 1, tzinfo=UTC)
    dataset_repository.save(
        Dataset(
            dataset_id="demo-dataset-evaluation",
            name="Demo Evaluation Set",
            version="v1.0",
            description="Older local registry metadata",
            storage_uri="memory://kavach/demo-evaluation",
            storage_type="memory",
            schema_version="1.0",
            record_count=120,
            checksum="demo-evaluation-v1-checksum",
            creator="studio-demo",
            created_at=original_created_at,
            status=DatasetStatus.FROZEN,
        )
    )
    monkeypatch.setattr(
        "kavach.api.demo_seed.dataset_object_store_from_environment",
        lambda: object_store,
    )
    monkeypatch.setenv("KAVACH_DATASET_S3_BUCKET", "local-datasets")

    seed_demo_registry_assets(
        prompt_repository,
        model_repository,
        dataset_repository,
    )

    dataset = dataset_repository.find_by_id("demo-dataset-evaluation")
    assert dataset is not None
    assert dataset.created_at == original_created_at
    assert dataset.storage_uri == "s3://local-datasets/demo/evaluation/v1.0/dataset.jsonl"
    assert dataset.storage_type == "S3"
    assert len(object_store.calls) == 1
    assert object_store.calls[0]["bucket"] == "local-datasets"
    assert object_store.calls[0]["key"] == "demo/evaluation/v1.0/dataset.jsonl"
    assert object_store.calls[0]["content_type"] == "application/x-ndjson"
    assert object_store.calls[0]["metadata"] == {
        "dataset_id": "demo-dataset-evaluation",
        "version": "v1.0",
    }
    assert len(object_store.calls[0]["body"].decode().splitlines()) == 120


def test_demo_experiment_graph_projection_covers_leaderboard_lineage() -> None:
    (
        experiment_repository,
        candidate_repository,
        run_repository,
        evaluation_repository,
        leaderboard_repository,
        prompt_repository,
        model_repository,
        dataset_repository,
    ) = _workflow_repositories()
    seed_demo_experiments(experiment_repository, minimum_count=5)
    seed_demo_registry_assets(prompt_repository, model_repository, dataset_repository)
    seed_demo_experiment_workflows(
        experiment_repository,
        candidate_repository,
        run_repository,
        evaluation_repository,
        leaderboard_repository,
    )
    graph_repository = InMemoryOntologyGraphRepository()

    synchronize_demo_experiment_graph(
        graph_repository,
        experiment_repository,
        candidate_repository,
        run_repository,
        evaluation_repository,
        leaderboard_repository,
        prompt_repository,
        model_repository,
        dataset_repository,
    )
    service = OntologyService(graph_repository)

    assert service.get_entity(EntityType.EXPERIMENT.value, "demo-experiment-01")
    assert service.get_entity(EntityType.CANDIDATE.value, "demo-experiment-01-baseline")
    assert service.get_entity(
        EntityType.LEADERBOARD.value,
        "demo-experiment-01-leaderboard",
    )
    assert service.find_relationships(
        EntityType.LEADERBOARD.value,
        "demo-experiment-01-leaderboard",
        relationship_type=RelationshipType.GENERATED_FROM.value,
        direction="outgoing",
    )
    assert service.find_relationships(
        EntityType.LEADERBOARD.value,
        "demo-experiment-01-leaderboard",
        relationship_type=RelationshipType.RECOMMENDS.value,
        direction="outgoing",
    )

    # A second startup reconciliation must not duplicate the projection.
    synchronize_demo_experiment_graph(
        graph_repository,
        experiment_repository,
        candidate_repository,
        run_repository,
        evaluation_repository,
        leaderboard_repository,
        prompt_repository,
        model_repository,
        dataset_repository,
    )


def test_demo_graph_query_service_resolves_repository_override() -> None:
    graph_repository = InMemoryOntologyGraphRepository()
    app = FastAPI()
    app.dependency_overrides[get_ontology_graph_query_repository] = (
        lambda: graph_repository
    )

    service = _resolve_graph_query_service(app)

    assert service is not None


def test_experiment_persistence_mapper_uses_created_at_for_legacy_rows() -> None:
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    record = {
        "experiment_id": "experiment-legacy",
        "name": "Legacy",
        "description": "Legacy row",
        "owner": "owner",
        "created_at": created_at.isoformat(),
        "status": "DRAFT",
    }

    reloaded = ExperimentPersistenceMapper.from_persistence_record(record)

    assert reloaded.updated_at == created_at


def test_sqlite_experiment_updated_at_survives_reload(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "experiments.db")
    database.initialize()
    repository = SQLiteExperimentRepository(database)
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    updated_at = created_at + timedelta(hours=2)
    experiment = Experiment(
        experiment_id="experiment-updated",
        name="Updated experiment",
        description="Persist modified time",
        owner="owner",
        created_at=created_at,
        updated_at=updated_at,
        status=ExperimentStatus.RUNNING,
    )

    repository.save(experiment)

    assert repository.find_by_id(experiment.experiment_id) == experiment


def test_sqlite_database_migrates_legacy_experiment_table(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE experiment ("
            "experiment_id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "description TEXT NOT NULL, owner TEXT NOT NULL, "
            "created_at TEXT NOT NULL, status TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO experiment VALUES (?, ?, ?, ?, ?, ?)",
            (
                "legacy-1",
                "Legacy",
                "Legacy row",
                "owner",
                "2026-07-01T00:00:00+00:00",
                "DRAFT",
            ),
        )

    SQLiteDatabase(path).initialize()

    with sqlite3.connect(path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(experiment)")
        }
        updated_at = connection.execute(
            "SELECT updated_at FROM experiment WHERE experiment_id = ?",
            ("legacy-1",),
        ).fetchone()[0]

    assert "updated_at" in columns
    assert updated_at == "2026-07-01T00:00:00+00:00"


def test_non_sqlite_experiment_repositories_include_updated_at_in_sql() -> None:
    assert "updated_at" in PostgresExperimentRepository._INSERT_EXPERIMENT_SQL
    assert "updated_at" in PostgresExperimentRepository._SELECT_EXPERIMENT_COLUMNS
    assert "updated_at" in SnowflakeExperimentRepository._MERGE_EXPERIMENT_SQL
    assert "updated_at" in SnowflakeExperimentRepository._SELECT_EXPERIMENT_COLUMNS


def test_non_sqlite_schemas_declare_updated_at() -> None:
    for schema_path in (
        "src/kavach/databases/postgres/schema.sql",
        "src/kavach/databases/snowflake/schema.sql",
    ):
        schema = Path(schema_path).read_text(encoding="utf-8")
        assert "updated_at" in schema
