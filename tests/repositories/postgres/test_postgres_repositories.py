import pytest
from datetime import UTC, datetime

from kavach.databases.postgres.database import PostgresDatabase
from kavach.decisions import (
    DecisionEvidenceReference,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionStatus,
    DecisionTarget,
    DecisionTargetType,
    GovernanceDecision,
)
from kavach.repositories.dataset_repository import DatasetRepository
from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from kavach.repositories.experiment_repository import ExperimentRepository
from kavach.repositories.leaderboard_repository import (
    LeaderboardRepository,
)
from kavach.repositories.model_repository import ModelRepository
from kavach.repositories.postgres.postgres_dataset_repository import (
    PostgresDatasetRepository,
)
from kavach.repositories.postgres.postgres_evaluation_repository import (
    PostgresEvaluationRepository,
)
from kavach.repositories.postgres.postgres_evaluation_run_repository import (
    PostgresEvaluationRunRepository,
)
from kavach.repositories.postgres.postgres_governance_decision_repository import (
    PostgresGovernanceDecisionRepository,
)
from kavach.repositories.postgres.postgres_experiment_candidate_repository import (
    PostgresExperimentCandidateRepository,
)
from kavach.repositories.postgres.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from kavach.repositories.postgres.postgres_leaderboard_repository import (
    PostgresLeaderboardRepository,
)
from kavach.repositories.postgres.postgres_model_repository import (
    PostgresModelRepository,
)
from kavach.repositories.postgres.postgres_policy_administration_repository import (
    PostgresPolicyAdministrationRepository,
)
from kavach.repositories.postgres.postgres_prompt_repository import (
    PostgresPromptRepository,
)
from kavach.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)
from kavach.repositories.prompt_repository import PromptRepository
from tests.repositories.contract.test_dataset_repository_contract import (
    DatasetRepositoryContract,
)
from tests.repositories.contract.test_evaluation_repository_contract import (
    EvaluationRepositoryContract,
)
from tests.repositories.contract.test_evaluation_run_repository_contract import (
    EvaluationRunRepositoryContract,
)
from tests.repositories.contract.test_experiment_candidate_repository_contract import (
    ExperimentCandidateRepositoryContract,
)
from tests.repositories.contract.test_experiment_repository_contract import (
    ExperimentRepositoryContract,
)
from tests.repositories.contract.test_leaderboard_repository_contract import (
    LeaderboardRepositoryContract,
)
from tests.repositories.contract.test_model_repository_contract import (
    ModelRepositoryContract,
)
from tests.repositories.contract.test_policy_administration_repository_contract import (
    PolicyAdministrationRepositoryContract,
)
from tests.repositories.contract.test_prompt_repository_contract import (
    PromptRepositoryContract,
)


class TestPostgresEvaluationRepository(EvaluationRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresEvaluationRepository(postgres_database)

    def repository(self) -> EvaluationRepository:
        return self._repository


class TestPostgresPromptRepository(PromptRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresPromptRepository(postgres_database)

    def repository(self) -> PromptRepository:
        return self._repository


class TestPostgresModelRepository(ModelRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresModelRepository(postgres_database)

    def repository(self) -> ModelRepository:
        return self._repository


class TestPostgresDatasetRepository(DatasetRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresDatasetRepository(postgres_database)

    def repository(self) -> DatasetRepository:
        return self._repository


class TestPostgresExperimentRepository(ExperimentRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresExperimentRepository(postgres_database)

    def repository(self) -> ExperimentRepository:
        return self._repository


class TestPostgresExperimentCandidateRepository(
    ExperimentCandidateRepositoryContract
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresExperimentCandidateRepository(
            postgres_database
        )

    def repository(self) -> ExperimentCandidateRepository:
        return self._repository


class TestPostgresEvaluationRunRepository(
    EvaluationRunRepositoryContract
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresEvaluationRunRepository(postgres_database)

    def repository(self) -> EvaluationRunRepository:
        return self._repository


class TestPostgresLeaderboardRepository(LeaderboardRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresLeaderboardRepository(postgres_database)

    def repository(self) -> LeaderboardRepository:
        return self._repository


class TestPostgresPolicyAdministrationRepository(
    PolicyAdministrationRepositoryContract,
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        self._repository = PostgresPolicyAdministrationRepository(
            postgres_database
        )

    def repository(self) -> PolicyAdministrationRepository:
        return self._repository


def test_postgres_governance_decision_repository_round_trip(
    postgres_database: PostgresDatabase,
) -> None:
    repository = PostgresGovernanceDecisionRepository(postgres_database)
    decision = GovernanceDecision.approved(
        decision_id="decision-1",
        target=DecisionTarget(
            target_type=DecisionTargetType.CANDIDATE,
            target_id="candidate-1",
        ),
        reason="Candidate passed governance.",
        evidence=(
            DecisionEvidenceReference(
                evidence_type="EvaluationResult",
                evidence_id="evaluation-result-1",
            ),
        ),
        policies=(
            DecisionPolicyReference(
                policy_id="policy-1",
                policy_version="2026-07-02",
            ),
        ),
        provenance=DecisionProvenance(
            producer_type=DecisionProducerType.POLICY_ENGINE,
            producer_id="policy-engine-1",
            actor_id="governance-admin",
            correlation_id="correlation-1",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        ),
        finalized_at=datetime(2026, 7, 2, 1, tzinfo=UTC),
    )

    repository.save(decision)
    archived = repository.archive(
        "decision-1",
        reason="No longer current.",
    )

    assert repository.get("decision-1") == archived
    assert archived.status == DecisionStatus.ARCHIVED
    assert repository.find_by_correlation_id("correlation-1") == (archived,)
    assert repository.find_by_request_id("request-1") == (archived,)
    assert repository.list() == (archived,)
