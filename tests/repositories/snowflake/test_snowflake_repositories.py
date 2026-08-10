import pytest

from ai_governance.databases.snowflake.database import SnowflakeDatabase
from ai_governance.repositories.dataset_repository import DatasetRepository
from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from ai_governance.repositories.experiment_repository import ExperimentRepository
from ai_governance.repositories.leaderboard_repository import (
    LeaderboardRepository,
)
from ai_governance.repositories.model_repository import ModelRepository
from ai_governance.repositories.prompt_repository import PromptRepository
from ai_governance.repositories.snowflake.snowflake_dataset_repository import (
    SnowflakeDatasetRepository,
)
from ai_governance.repositories.snowflake.snowflake_evaluation_repository import (
    SnowflakeEvaluationRepository,
)
from ai_governance.repositories.snowflake.snowflake_evaluation_run_repository import (
    SnowflakeEvaluationRunRepository,
)
from ai_governance.repositories.snowflake.snowflake_experiment_candidate_repository import (
    SnowflakeExperimentCandidateRepository,
)
from ai_governance.repositories.snowflake.snowflake_experiment_repository import (
    SnowflakeExperimentRepository,
)
from ai_governance.repositories.snowflake.snowflake_leaderboard_repository import (
    SnowflakeLeaderboardRepository,
)
from ai_governance.repositories.snowflake.snowflake_model_repository import (
    SnowflakeModelRepository,
)
from ai_governance.repositories.snowflake.snowflake_prompt_repository import (
    SnowflakePromptRepository,
)
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
from tests.repositories.contract.test_prompt_repository_contract import (
    PromptRepositoryContract,
)


class TestSnowflakeEvaluationRepository(EvaluationRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        snowflake_database: SnowflakeDatabase,
    ) -> None:
        self._repository = SnowflakeEvaluationRepository(snowflake_database)

    def repository(self) -> EvaluationRepository:
        return self._repository


class TestSnowflakePromptRepository(PromptRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        snowflake_database: SnowflakeDatabase,
    ) -> None:
        self._repository = SnowflakePromptRepository(snowflake_database)

    def repository(self) -> PromptRepository:
        return self._repository


class TestSnowflakeModelRepository(ModelRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        snowflake_database: SnowflakeDatabase,
    ) -> None:
        self._repository = SnowflakeModelRepository(snowflake_database)

    def repository(self) -> ModelRepository:
        return self._repository


class TestSnowflakeDatasetRepository(DatasetRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        snowflake_database: SnowflakeDatabase,
    ) -> None:
        self._repository = SnowflakeDatasetRepository(snowflake_database)

    def repository(self) -> DatasetRepository:
        return self._repository


class TestSnowflakeExperimentRepository(ExperimentRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        snowflake_database: SnowflakeDatabase,
    ) -> None:
        self._repository = SnowflakeExperimentRepository(snowflake_database)

    def repository(self) -> ExperimentRepository:
        return self._repository


class TestSnowflakeExperimentCandidateRepository(
    ExperimentCandidateRepositoryContract
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        snowflake_database: SnowflakeDatabase,
    ) -> None:
        self._repository = SnowflakeExperimentCandidateRepository(
            snowflake_database
        )

    def repository(self) -> ExperimentCandidateRepository:
        return self._repository


class TestSnowflakeEvaluationRunRepository(
    EvaluationRunRepositoryContract
):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        snowflake_database: SnowflakeDatabase,
    ) -> None:
        self._repository = SnowflakeEvaluationRunRepository(
            snowflake_database
        )

    def repository(self) -> EvaluationRunRepository:
        return self._repository


class TestSnowflakeLeaderboardRepository(LeaderboardRepositoryContract):
    @pytest.fixture(autouse=True)
    def setup(
        self,
        snowflake_database: SnowflakeDatabase,
    ) -> None:
        self._repository = SnowflakeLeaderboardRepository(snowflake_database)

    def repository(self) -> LeaderboardRepository:
        return self._repository
