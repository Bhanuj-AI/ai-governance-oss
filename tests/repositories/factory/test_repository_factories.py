"""Tests for repository factories."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ai_governance.settings import Settings


def _minimal_settings(
    *,
    policy_repository: str = "inmemory",
    policy_sqlite_path: str | None = None,
    evaluation_repository: str = "inmemory",
    evaluation_sqlite_path: str | None = None,
    experiment_repository: str = "inmemory",
    experiment_sqlite_path: str | None = None,
    experiment_candidate_repository: str = "inmemory",
    experiment_candidate_sqlite_path: str | None = None,
    evaluation_run_repository: str = "inmemory",
    evaluation_run_sqlite_path: str | None = None,
    leaderboard_repository: str = "inmemory",
    leaderboard_sqlite_path: str | None = None,
    prompt_repository: str = "inmemory",
    prompt_sqlite_path: str | None = None,
    model_repository: str = "inmemory",
    model_sqlite_path: str | None = None,
    dataset_repository: str = "inmemory",
    dataset_sqlite_path: str | None = None,
    job_repository: str = "inmemory",
    job_sqlite_path: str | None = None,
    governance_decision_repository: str = "inmemory",
    governance_decision_sqlite_path: str | None = None,
    ontology_sync_event_repository: str = "inmemory",
    ontology_sync_event_sqlite_path: str | None = None,
    ontology_repository: str = "inmemory",
    ontology_sqlite_path: str | None = None,
    postgres_dsn: str | None = None,
) -> Settings:
    """Build a Settings instance with defaults for all fields."""

    return Settings(
        # Policy administration
        policy_repository=policy_repository,
        policy_sqlite_path=policy_sqlite_path,
        policy_postgres_dsn=postgres_dsn,

        # Evaluation
        evaluation_repository=evaluation_repository,
        evaluation_sqlite_path=evaluation_sqlite_path,
        evaluation_postgres_dsn=postgres_dsn,

        # Experiment
        experiment_repository=experiment_repository,
        experiment_sqlite_path=experiment_sqlite_path,
        experiment_postgres_dsn=postgres_dsn,

        # Experiment Candidate
        experiment_candidate_repository=experiment_candidate_repository,
        experiment_candidate_sqlite_path=experiment_candidate_sqlite_path,
        experiment_candidate_postgres_dsn=postgres_dsn,

        # Evaluation Run
        evaluation_run_repository=evaluation_run_repository,
        evaluation_run_sqlite_path=evaluation_run_sqlite_path,
        evaluation_run_postgres_dsn=postgres_dsn,

        # Leaderboard
        leaderboard_repository=leaderboard_repository,
        leaderboard_sqlite_path=leaderboard_sqlite_path,
        leaderboard_postgres_dsn=postgres_dsn,

        # Prompt
        prompt_repository=prompt_repository,
        prompt_sqlite_path=prompt_sqlite_path,
        prompt_postgres_dsn=postgres_dsn,

        # Model
        model_repository=model_repository,
        model_sqlite_path=model_sqlite_path,
        model_postgres_dsn=postgres_dsn,

        # Dataset
        dataset_repository=dataset_repository,
        dataset_sqlite_path=dataset_sqlite_path,
        dataset_postgres_dsn=postgres_dsn,

        # Job
        job_repository=job_repository,
        job_sqlite_path=job_sqlite_path,
        job_postgres_dsn=postgres_dsn,

        # Governance Decision
        governance_decision_repository=governance_decision_repository,
        governance_decision_sqlite_path=governance_decision_sqlite_path,
        governance_decision_postgres_dsn=postgres_dsn,

        # Ontology Sync Event
        ontology_sync_event_repository=ontology_sync_event_repository,
        ontology_sync_event_sqlite_path=ontology_sync_event_sqlite_path,
        ontology_sync_event_postgres_dsn=postgres_dsn,

        # Ontology Graph
        ontology_repository=ontology_repository,
        ontology_sqlite_path=ontology_sqlite_path,
        ontology_postgres_dsn=postgres_dsn,
    )


class TestPolicyRepositoryFactory:
    def test_sqlite_is_initialized_and_writable(self, tmp_path):
        from ai_governance.ontology.demo_seed import seed_demo_policy_administration
        from ai_governance.repositories.factories import PolicyRepositoryFactory

        path = str(tmp_path / "ai_governance.db")
        repository = PolicyRepositoryFactory(
            _minimal_settings(
                policy_repository="sqlite",
                policy_sqlite_path=path,
            )
        ).create()

        policy_id = seed_demo_policy_administration(repository)

        assert repository.get_definition(policy_id) is not None


class TestEvaluationRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import EvaluationRepositoryFactory
        from ai_governance.repositories.in_memory_evaluation_repository import (
            InMemoryEvaluationRepository,
        )

        repo = EvaluationRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryEvaluationRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import EvaluationRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_evaluation_repository import SQLiteEvaluationRepository

        path = str(tmp_path / "eval.db")
        repo = EvaluationRepositoryFactory(
            _minimal_settings(evaluation_repository="sqlite", evaluation_sqlite_path=path)
        ).create()
        assert isinstance(repo, SQLiteEvaluationRepository)

    def test_sqlite_missing_path_raises(self):
        from ai_governance.repositories.factories import EvaluationRepositoryFactory

        with pytest.raises(ValueError, match="AI_GOVERNANCE_EVALUATION_SQLITE_PATH"):
            EvaluationRepositoryFactory(
                _minimal_settings(evaluation_repository="sqlite")
            ).create()

    def test_postgres_requires_dsn(self):
        from ai_governance.repositories.factories import EvaluationRepositoryFactory

        with pytest.raises(
            ValueError, match="AI_GOVERNANCE_EVALUATION_POSTGRES_DSN"
        ):
            EvaluationRepositoryFactory(
                _minimal_settings(evaluation_repository="postgres")
            ).create()

    def test_invalid_backend_raises(self):
        from ai_governance.repositories.factories import EvaluationRepositoryFactory

        with pytest.raises(ValueError, match="Unsupported evaluation repository backend"):
            EvaluationRepositoryFactory(
                _minimal_settings(evaluation_repository="redis")
            ).create()


class TestExperimentRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import ExperimentRepositoryFactory
        from ai_governance.repositories.in_memory_experiment_repository import (
            InMemoryExperimentRepository,
        )

        repo = ExperimentRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryExperimentRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import ExperimentRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_experiment_repository import SQLiteExperimentRepository

        path = str(tmp_path / "exp.db")
        repo = ExperimentRepositoryFactory(
            _minimal_settings(experiment_repository="sqlite", experiment_sqlite_path=path)
        ).create()
        assert isinstance(repo, SQLiteExperimentRepository)


class TestJobRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import JobRepositoryFactory
        from ai_governance.repositories import InMemoryJobRepository

        repo = JobRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryJobRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import JobRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_job_repository import SQLiteJobRepository

        path = str(tmp_path / "jobs.db")
        repo = JobRepositoryFactory(
            _minimal_settings(job_repository="sqlite", job_sqlite_path=path)
        ).create()
        assert isinstance(repo, SQLiteJobRepository)

    def test_postgres(self, monkeypatch):
        from ai_governance.databases.postgres.database import PostgresDatabase
        from ai_governance.repositories.factories import JobRepositoryFactory
        from ai_governance.repositories.postgres import PostgresJobRepository

        monkeypatch.setattr(PostgresDatabase, "initialize", lambda _database: None)
        repo = JobRepositoryFactory(
            _minimal_settings(
                job_repository="postgres",
                postgres_dsn="postgresql://user:pass@db.example/ai-governance",
            )
        ).create()

        assert isinstance(repo, PostgresJobRepository)


class TestReplayExecutionStoreFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import ReplayExecutionStoreFactory
        from ai_governance.services.replay_execution_discovery import InMemoryReplaySourceResolver

        store = ReplayExecutionStoreFactory(_minimal_settings()).create()

        assert isinstance(store, InMemoryReplaySourceResolver)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import ReplayExecutionStoreFactory
        from ai_governance.repositories.sqlite.sqlite_replay_execution_store import (
            SQLiteReplayExecutionStore,
        )

        store = ReplayExecutionStoreFactory(
            replace(
                _minimal_settings(),
                replay_execution_catalog_backend="sqlite",
                replay_execution_catalog_sqlite_path=str(tmp_path / "replay.db"),
            )
        ).create()

        assert isinstance(store, SQLiteReplayExecutionStore)

    def test_postgres(self, monkeypatch):
        from ai_governance.databases.postgres.database import PostgresDatabase
        from ai_governance.repositories.factories import ReplayExecutionStoreFactory
        from ai_governance.repositories.postgres.postgres_replay_execution_store import (
            PostgresReplayExecutionStore,
        )

        monkeypatch.setattr(PostgresDatabase, "initialize", lambda _database: None)
        store = ReplayExecutionStoreFactory(
            replace(
                _minimal_settings(postgres_dsn="postgresql://user:pass@db.example/ai-governance"),
                replay_execution_catalog_backend="postgres",
                replay_postgres_dsn="postgresql://user:pass@db.example/ai-governance",
            )
        ).create()

        assert isinstance(store, PostgresReplayExecutionStore)

    def test_durable_backends_require_their_configuration(self):
        from ai_governance.repositories.factories import ReplayExecutionStoreFactory

        with pytest.raises(ValueError, match="AI_GOVERNANCE_REPLAY_EXECUTION_CATALOG_SQLITE_PATH"):
            ReplayExecutionStoreFactory(
                replace(_minimal_settings(), replay_execution_catalog_backend="sqlite")
            ).create()
        with pytest.raises(ValueError, match="AI_GOVERNANCE_REPLAY_POSTGRES_DSN"):
            ReplayExecutionStoreFactory(
                replace(_minimal_settings(), replay_execution_catalog_backend="postgres")
            ).create()


class TestGovernanceDecisionRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import GovernanceDecisionRepositoryFactory

        repo = GovernanceDecisionRepositoryFactory(
            _minimal_settings()
        ).create()
        assert repo is not None

    def test_inmemory_with_publisher(self):
        from ai_governance.repositories.factories import GovernanceDecisionRepositoryFactory

        class FakePublisher:
            pass

        repo = GovernanceDecisionRepositoryFactory(
            _minimal_settings()
        ).create(ontology_event_publisher=FakePublisher())
        assert repo is not None


class TestOntologySyncEventRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import OntologySyncEventRepositoryFactory
        from ai_governance.repositories import InMemoryOntologySyncEventRepository

        repo = OntologySyncEventRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryOntologySyncEventRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import OntologySyncEventRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_ontology_sync_event_repository import SQLiteOntologySyncEventRepository

        path = str(tmp_path / "sync.db")
        repo = OntologySyncEventRepositoryFactory(
            _minimal_settings(
                ontology_sync_event_repository="sqlite",
                ontology_sync_event_sqlite_path=path,
            )
        ).create()
        assert isinstance(repo, SQLiteOntologySyncEventRepository)

    def test_postgres(self, monkeypatch):
        from ai_governance.databases.postgres.database import PostgresDatabase
        from ai_governance.repositories.factories import OntologySyncEventRepositoryFactory
        from ai_governance.repositories.postgres import PostgresOntologySyncEventRepository

        monkeypatch.setattr(PostgresDatabase, "initialize", lambda _database: None)
        repo = OntologySyncEventRepositoryFactory(
            _minimal_settings(
                ontology_sync_event_repository="postgres",
                postgres_dsn="postgresql://user:pass@db.example/ai-governance",
            )
        ).create()

        assert isinstance(repo, PostgresOntologySyncEventRepository)


class TestOntologyGraphRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import OntologyGraphRepositoryFactory
        from ai_governance.ontology import InMemoryOntologyGraphRepository

        repo = OntologyGraphRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryOntologyGraphRepository)

    def test_sqlite_not_implemented(self):
        from ai_governance.repositories.factories import OntologyGraphRepositoryFactory

        with pytest.raises(
            ValueError, match="AI_GOVERNANCE_ONTOLOGY_REPOSITORY=sqlite"
        ):
            OntologyGraphRepositoryFactory(
                _minimal_settings(ontology_repository="sqlite")
            ).create()


class TestPromptRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import PromptRepositoryFactory
        from ai_governance.repositories.in_memory_prompt_repository import (
            InMemoryPromptRepository,
        )

        repo = PromptRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryPromptRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import PromptRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_prompt_repository import SQLitePromptRepository

        path = str(tmp_path / "prompts.db")
        repo = PromptRepositoryFactory(
            _minimal_settings(prompt_repository="sqlite", prompt_sqlite_path=path)
        ).create()
        assert isinstance(repo, SQLitePromptRepository)


class TestModelRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import ModelRepositoryFactory
        from ai_governance.repositories.in_memory_model_repository import (
            InMemoryModelRepository,
        )

        repo = ModelRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryModelRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import ModelRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_model_repository import SQLiteModelRepository

        path = str(tmp_path / "models.db")
        repo = ModelRepositoryFactory(
            _minimal_settings(model_repository="sqlite", model_sqlite_path=path)
        ).create()
        assert isinstance(repo, SQLiteModelRepository)


class TestDatasetRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import DatasetRepositoryFactory
        from ai_governance.repositories.in_memory_dataset_repository import (
            InMemoryDatasetRepository,
        )

        repo = DatasetRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryDatasetRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import DatasetRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_dataset_repository import SQLiteDatasetRepository

        path = str(tmp_path / "datasets.db")
        repo = DatasetRepositoryFactory(
            _minimal_settings(dataset_repository="sqlite", dataset_sqlite_path=path)
        ).create()
        assert isinstance(repo, SQLiteDatasetRepository)


class TestLeaderboardRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import LeaderboardRepositoryFactory
        from ai_governance.repositories.in_memory_leaderboard_repository import (
            InMemoryLeaderboardRepository,
        )

        repo = LeaderboardRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryLeaderboardRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import LeaderboardRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_leaderboard_repository import SQLiteLeaderboardRepository

        path = str(tmp_path / "leaderboard.db")
        repo = LeaderboardRepositoryFactory(
            _minimal_settings(
                leaderboard_repository="sqlite", leaderboard_sqlite_path=path
            )
        ).create()
        assert isinstance(repo, SQLiteLeaderboardRepository)


class TestExperimentCandidateRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import (
            ExperimentCandidateRepositoryFactory,
        )
        from ai_governance.repositories.in_memory_experiment_candidate_repository import (
            InMemoryExperimentCandidateRepository,
        )

        repo = ExperimentCandidateRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryExperimentCandidateRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import (
            ExperimentCandidateRepositoryFactory,
        )
        from ai_governance.repositories.sqlite.sqlite_experiment_candidate_repository import SQLiteExperimentCandidateRepository

        path = str(tmp_path / "candidates.db")
        repo = ExperimentCandidateRepositoryFactory(
            _minimal_settings(
                experiment_candidate_repository="sqlite",
                experiment_candidate_sqlite_path=path,
            )
        ).create()
        assert isinstance(repo, SQLiteExperimentCandidateRepository)


class TestEvaluationRunRepositoryFactory:
    def test_inmemory(self):
        from ai_governance.repositories.factories import EvaluationRunRepositoryFactory
        from ai_governance.repositories.in_memory_evaluation_run_repository import (
            InMemoryEvaluationRunRepository,
        )

        repo = EvaluationRunRepositoryFactory(_minimal_settings()).create()
        assert isinstance(repo, InMemoryEvaluationRunRepository)

    def test_sqlite(self, tmp_path):
        from ai_governance.repositories.factories import EvaluationRunRepositoryFactory
        from ai_governance.repositories.sqlite.sqlite_evaluation_run_repository import SQLiteEvaluationRunRepository

        path = str(tmp_path / "runs.db")
        repo = EvaluationRunRepositoryFactory(
            _minimal_settings(
                evaluation_run_repository="sqlite",
                evaluation_run_sqlite_path=path,
            )
        ).create()
        assert isinstance(repo, SQLiteEvaluationRunRepository)


class TestConfigDrivenBehavior:
    """Tests that verify config-driven behavior at the dependency level."""

    def test_default_backend_is_inmemory(self):
        """All repositories default to in-memory when no env vars are set."""
        from ai_governance.settings import load_settings

        settings = load_settings()
        assert settings.evaluation_repository == "inmemory"
        assert settings.experiment_repository == "inmemory"
        assert settings.job_repository == "inmemory"

    def test_sqlite_backend_requires_path(self):
        """SQLite backends fail fast when path is not configured."""
        from ai_governance.repositories.factories import EvaluationRepositoryFactory

        settings = _minimal_settings(evaluation_repository="sqlite")
        with pytest.raises(ValueError, match="AI_GOVERNANCE_EVALUATION_SQLITE_PATH"):
            EvaluationRepositoryFactory(settings).create()

    def test_unsupported_backend_raises_clearly(self):
        """Unknown backends produce a clear error message."""
        from ai_governance.repositories.factories import JobRepositoryFactory

        settings = _minimal_settings(job_repository="redis")
        with pytest.raises(ValueError, match="Unsupported job repository backend"):
            JobRepositoryFactory(settings).create()


@pytest.mark.parametrize(
    ("repository_field", "factory_name", "repository_name"),
    (
        ("evaluation_repository", "EvaluationRepositoryFactory", "PostgresEvaluationRepository"),
        ("experiment_repository", "ExperimentRepositoryFactory", "PostgresExperimentRepository"),
        ("experiment_candidate_repository", "ExperimentCandidateRepositoryFactory", "PostgresExperimentCandidateRepository"),
        ("evaluation_run_repository", "EvaluationRunRepositoryFactory", "PostgresEvaluationRunRepository"),
        ("leaderboard_repository", "LeaderboardRepositoryFactory", "PostgresLeaderboardRepository"),
        ("prompt_repository", "PromptRepositoryFactory", "PostgresPromptRepository"),
        ("model_repository", "ModelRepositoryFactory", "PostgresModelRepository"),
        ("dataset_repository", "DatasetRepositoryFactory", "PostgresDatasetRepository"),
        ("governance_decision_repository", "GovernanceDecisionRepositoryFactory", "PostgresGovernanceDecisionRepository"),
    ),
)
def test_postgres_factories_select_existing_repository_implementations(
    repository_field: str,
    factory_name: str,
    repository_name: str,
) -> None:
    """PostgreSQL selection must be available without a live database connection."""
    from ai_governance.repositories import factories
    from ai_governance.repositories import postgres

    settings = replace(
        _minimal_settings(postgres_dsn="postgresql://user:pass@db.example/ai-governance"),
        **{repository_field: "postgres"},
    )

    repository = getattr(factories, factory_name)(settings).create()

    assert isinstance(repository, getattr(postgres, repository_name))
