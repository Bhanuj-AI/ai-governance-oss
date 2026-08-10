from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from ai_governance.databases.postgres.database import PostgresDatabase


class TestPostgresDatabase:
    def test_should_create_schema(
        self,
        postgres_database: PostgresDatabase,
    ) -> None:
        with postgres_database.connect() as connection:
            cursor = connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                """
            )

            tables = {row["table_name"] for row in cursor.fetchall()}

        assert "agent_evaluation" in tables
        assert "dataset_registry" in tables
        assert "evaluation_run" in tables
        assert "experiment" in tables
        assert "experiment_candidate" in tables
        assert "leaderboard" in tables
        assert "leaderboard_entry" in tables
        assert "model_registry" in tables
        assert "prompt_registry" in tables
        assert "replay_workflow_execution" in tables


def test_initialize_serializes_schema_ddl(monkeypatch) -> None:
    class Connection:
        def __init__(self) -> None:
            self.executed: list[tuple[str, tuple[int, ...] | None]] = []
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def execute(self, statement: str, parameters=None) -> None:
            self.executed.append((statement, parameters))

        def commit(self) -> None:
            self.committed = True

    connection = Connection()
    database = PostgresDatabase("postgresql://unused")
    monkeypatch.setattr(database, "connect", lambda: connection)

    database.initialize()

    assert connection.executed[0] == (
        "SELECT pg_advisory_xact_lock(%s)",
        (278_460_749,),
    )
    assert "CREATE TABLE IF NOT EXISTS" in connection.executed[1][0]
    assert connection.committed


def test_concurrent_initialization_completes_without_ddl_deadlock(
    postgres_database: PostgresDatabase,
) -> None:
    barrier = Barrier(2)

    def initialize() -> None:
        barrier.wait()
        PostgresDatabase(postgres_database.dsn).initialize()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(initialize) for _ in range(2)]
        for future in futures:
            future.result()
