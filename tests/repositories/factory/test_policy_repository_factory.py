"""Tests for PolicyRepositoryFactory."""

import pytest

from ai_governance.repositories.factories.policy_repository_factory import (
    PolicyRepositoryFactory,
)
from ai_governance.repositories.in_memory_policy_administration_repository import (
    InMemoryPolicyAdministrationRepository,
)
from ai_governance.repositories.postgres import (
    PostgresPolicyAdministrationRepository,
)
from ai_governance.repositories.sqlite import (
    SQLitePolicyAdministrationRepository,
)
from ai_governance.settings import Settings


def _minimal_settings(
    *,
    policy_repository: str = "inmemory",
    policy_sqlite_path: str | None = None,
    policy_postgres_dsn: str | None = None,
) -> Settings:
    """Build a Settings instance with defaults for all non-policy fields."""

    return Settings(
        # Policy administration
        policy_repository=policy_repository,
        policy_sqlite_path=policy_sqlite_path,
        policy_postgres_dsn=policy_postgres_dsn,

        # Evaluation
        evaluation_repository="inmemory",
        evaluation_sqlite_path=None,
        evaluation_postgres_dsn=None,

        # Experiment
        experiment_repository="inmemory",
        experiment_sqlite_path=None,
        experiment_postgres_dsn=None,

        # Experiment Candidate
        experiment_candidate_repository="inmemory",
        experiment_candidate_sqlite_path=None,
        experiment_candidate_postgres_dsn=None,

        # Evaluation Run
        evaluation_run_repository="inmemory",
        evaluation_run_sqlite_path=None,
        evaluation_run_postgres_dsn=None,

        # Leaderboard
        leaderboard_repository="inmemory",
        leaderboard_sqlite_path=None,
        leaderboard_postgres_dsn=None,

        # Prompt
        prompt_repository="inmemory",
        prompt_sqlite_path=None,
        prompt_postgres_dsn=None,

        # Model
        model_repository="inmemory",
        model_sqlite_path=None,
        model_postgres_dsn=None,

        # Dataset
        dataset_repository="inmemory",
        dataset_sqlite_path=None,
        dataset_postgres_dsn=None,

        # Job
        job_repository="inmemory",
        job_sqlite_path=None,
        job_postgres_dsn=None,

        # Governance Decision
        governance_decision_repository="inmemory",
        governance_decision_sqlite_path=None,
        governance_decision_postgres_dsn=None,

        # Ontology Sync Event
        ontology_sync_event_repository="inmemory",
        ontology_sync_event_sqlite_path=None,
        ontology_sync_event_postgres_dsn=None,

        # Ontology Graph
        ontology_repository="inmemory",
        ontology_sqlite_path=None,
        ontology_postgres_dsn=None,
    )


class TestPolicyRepositoryFactory:
    """Test cases for PolicyRepositoryFactory."""

    def test_create_inmemory_repository(self):
        settings = _minimal_settings(policy_repository="inmemory")

        repo = PolicyRepositoryFactory(settings).create()

        assert isinstance(repo, InMemoryPolicyAdministrationRepository)

    def test_create_sqlite_repository(self):
        settings = _minimal_settings(
            policy_repository="sqlite",
            policy_sqlite_path="/tmp/test.db",
        )

        repo = PolicyRepositoryFactory(settings).create()

        assert isinstance(repo, SQLitePolicyAdministrationRepository)

    def test_create_postgres_repository(self):
        settings = _minimal_settings(
            policy_repository="postgres",
            policy_postgres_dsn="postgresql://user:pass@localhost/db",
        )

        repo = PolicyRepositoryFactory(settings).create()

        assert isinstance(repo, PostgresPolicyAdministrationRepository)
        assert repo._database.dsn == "postgresql://user:pass@localhost/db"

    def test_create_sqlite_missing_path_raises_error(self):
        settings = _minimal_settings(
            policy_repository="sqlite",
            policy_sqlite_path=None,
        )

        with pytest.raises(ValueError, match="AI_GOVERNANCE_POLICY_SQLITE_PATH"):
            PolicyRepositoryFactory(settings).create()

    def test_create_postgres_missing_dsn_raises_error(self):
        settings = _minimal_settings(
            policy_repository="postgres",
            policy_postgres_dsn=None,
        )

        with pytest.raises(ValueError, match="AI_GOVERNANCE_POLICY_POSTGRES_DSN"):
            PolicyRepositoryFactory(settings).create()

    def test_create_invalid_repository_type_raises_error(self):
        settings = _minimal_settings(policy_repository="invalid")

        repo = PolicyRepositoryFactory(settings).create()
        assert isinstance(repo, InMemoryPolicyAdministrationRepository)
