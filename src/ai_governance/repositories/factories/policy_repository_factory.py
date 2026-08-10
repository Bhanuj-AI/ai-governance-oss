import logging
from ai_governance.settings import Settings
from ai_governance.repositories.in_memory_policy_administration_repository import (
    InMemoryPolicyAdministrationRepository,
)
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)
from ai_governance.repositories.sqlite import SQLitePolicyAdministrationRepository
from ai_governance.repositories.postgres import PostgresPolicyAdministrationRepository

logger = logging.getLogger(__name__)

class PolicyRepositoryFactory:
    """
    Selects the concrete PolicyAdministrationRepository implementation from runtime configuration.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
    
    def create(self) -> PolicyAdministrationRepository:
        # Log the repository type being selected for debugging purposes
        logger.info(f"Creating policy administration repository of type: {self._settings.policy_repository}")

        match self._settings.policy_repository:
            case "inmemory":

                logger.debug("Selected in-memory repository")
                return InMemoryPolicyAdministrationRepository()

            case "sqlite":
                if not self._settings.policy_sqlite_path:
                    error_msg = (
                        "AI_GOVERNANCE_POLICY_SQLITE_PATH is required when "
                        "AI_GOVERNANCE_POLICY_REPOSITORY=sqlite"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                logger.debug(f"Selected SQLite repository with path: {self._settings.policy_sqlite_path}")
                from ai_governance.repositories.factories.sqlite_database import (
                    create_sqlite_database,
                )

                return SQLitePolicyAdministrationRepository(
                    create_sqlite_database(self._settings.policy_sqlite_path)
                )

            case "postgres":
                if not self._settings.policy_postgres_dsn:
                    error_msg = (
                        "AI_GOVERNANCE_POLICY_POSTGRES_DSN is required when "
                        "AI_GOVERNANCE_POLICY_REPOSITORY=postgres"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                logger.debug("Selected PostgreSQL repository")
                from ai_governance.databases.postgres.database import PostgresDatabase

                return PostgresPolicyAdministrationRepository(
                    PostgresDatabase(self._settings.policy_postgres_dsn)
                )

            case _:
                warning_msg = (
                    f"Unsupported policy repository backend: {self._settings.policy_repository}. "
                    "Falling back to in-memory repository."
                )
                logger.warning(warning_msg)
                return InMemoryPolicyAdministrationRepository()
