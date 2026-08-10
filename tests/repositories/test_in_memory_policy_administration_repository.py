from ai_governance.repositories import InMemoryPolicyAdministrationRepository
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)
from tests.repositories.contract.test_policy_administration_repository_contract import (
    PolicyAdministrationRepositoryContract,
)


class TestInMemoryPolicyAdministrationRepository(
    PolicyAdministrationRepositoryContract,
):
    def repository(self) -> PolicyAdministrationRepository:
        return InMemoryPolicyAdministrationRepository()
