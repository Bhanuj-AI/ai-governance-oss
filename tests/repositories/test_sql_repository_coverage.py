from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from ai_governance.domain.datasets import Dataset, DatasetStatus
from ai_governance.domain.evaluation_result import EvaluationMetric, EvaluationResult
from ai_governance.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
    Leaderboard,
    LeaderboardEntry,
)
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.repositories.mappers.dataset_persistence_mapper import (
    DatasetPersistenceMapper,
)
from ai_governance.repositories.mappers.evaluation_persistence_mapper import (
    EvaluationPersistenceMapper,
)
from ai_governance.repositories.mappers.evaluation_run_persistence_mapper import (
    EvaluationRunPersistenceMapper,
)
from ai_governance.repositories.mappers.experiment_candidate_persistence_mapper import (
    ExperimentCandidatePersistenceMapper,
)
from ai_governance.repositories.mappers.experiment_persistence_mapper import (
    ExperimentPersistenceMapper,
)
from ai_governance.repositories.mappers.leaderboard_persistence_mapper import (
    LeaderboardPersistenceMapper,
)
from ai_governance.repositories.mappers.model_persistence_mapper import (
    ModelPersistenceMapper,
)
from ai_governance.repositories.mappers.prompt_persistence_mapper import (
    PromptPersistenceMapper,
)
from ai_governance.repositories.postgres.postgres_dataset_repository import (
    PostgresDatasetRepository,
)
from ai_governance.repositories.postgres.postgres_evaluation_repository import (
    PostgresEvaluationRepository,
)
from ai_governance.repositories.postgres.postgres_evaluation_run_repository import (
    PostgresEvaluationRunRepository,
)
from ai_governance.repositories.postgres.postgres_experiment_candidate_repository import (
    PostgresExperimentCandidateRepository,
)
from ai_governance.repositories.postgres.postgres_experiment_repository import (
    PostgresExperimentRepository,
)
from ai_governance.repositories.postgres.postgres_leaderboard_repository import (
    PostgresLeaderboardRepository,
)
from ai_governance.repositories.postgres.postgres_model_repository import (
    PostgresModelRepository,
)
from ai_governance.repositories.postgres.postgres_prompt_repository import (
    PostgresPromptRepository,
)
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


@dataclass(frozen=True)
class BackendSpec:
    name: str
    repository_class: type
    database_factory: Callable[..., Any]
    row_adapter: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RepositorySpec:
    name: str
    postgres_class: type
    snowflake_class: type
    entity: Any
    records: list[dict[str, Any]]
    save_method: str
    read_cases: tuple[tuple[str, tuple[Any, ...], list[list[dict[str, Any]]], Any], ...]
    none_case: tuple[str, tuple[Any, ...], list[list[dict[str, Any]]]]


class FakeResult:
    def __init__(
        self,
        rows: Sequence[dict[str, Any]] | None,
    ) -> None:
        self._rows = list(rows or [])

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class FakePostgresCursor:
    def __init__(
        self,
        connection: FakePostgresConnection,
    ) -> None:
        self._connection = connection

    def __enter__(self) -> FakePostgresCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def executemany(
        self,
        sql: str,
        records: Iterable[dict[str, Any]],
    ) -> None:
        self._connection.executed_many.append((sql, list(records)))
        if self._connection.fail_writes:
            raise RuntimeError("write failed")


class FakePostgresConnection:
    def __init__(
        self,
        database: FakePostgresDatabase,
    ) -> None:
        self._database = database
        self.fail_writes = database.fail_writes
        self.executed: list[tuple[str, dict[str, Any] | None]] = []
        self.executed_many: list[tuple[str, list[dict[str, Any]]]] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> FakePostgresConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> FakeResult:
        self.executed.append((sql, params))
        if self.fail_writes and sql.lstrip().upper().startswith(
            ("INSERT", "DELETE")
        ):
            raise RuntimeError("write failed")

        return FakeResult(self._database.next_rows())

    def cursor(self) -> FakePostgresCursor:
        return FakePostgresCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakePostgresDatabase:
    def __init__(
        self,
        rows: Sequence[Sequence[dict[str, Any]]] = (),
        fail_writes: bool = False,
    ) -> None:
        self._rows = [list(result_rows) for result_rows in rows]
        self.fail_writes = fail_writes
        self.connections: list[FakePostgresConnection] = []

    def connect(self) -> FakePostgresConnection:
        connection = FakePostgresConnection(self)
        self.connections.append(connection)
        return connection

    def next_rows(self) -> list[dict[str, Any]]:
        return self._rows.pop(0) if self._rows else []


class FakeSnowflakeCursor:
    def __init__(
        self,
        connection: FakeSnowflakeConnection,
    ) -> None:
        self._connection = connection
        self._current_rows: list[dict[str, Any]] = []

    def __enter__(self) -> FakeSnowflakeCursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> FakeSnowflakeCursor:
        self._connection.executed.append((sql, params))
        if self._connection.fail_writes and sql.lstrip().upper().startswith(
            ("MERGE", "INSERT", "DELETE")
        ):
            raise RuntimeError("write failed")

        self._current_rows = self._connection.database.next_rows()
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self._current_rows[0] if self._current_rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._current_rows)


class FakeSnowflakeConnection:
    def __init__(
        self,
        database: FakeSnowflakeDatabase,
    ) -> None:
        self.database = database
        self.fail_writes = database.fail_writes
        self.executed: list[tuple[str, dict[str, Any] | None]] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> FakeSnowflakeConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None

    def cursor(
        self,
        cursor_class: object | None = None,
    ) -> FakeSnowflakeCursor:
        return FakeSnowflakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeSnowflakeDatabase:
    def __init__(
        self,
        rows: Sequence[Sequence[dict[str, Any]]] = (),
        fail_writes: bool = False,
    ) -> None:
        self._rows = [list(result_rows) for result_rows in rows]
        self.fail_writes = fail_writes
        self.connections: list[FakeSnowflakeConnection] = []

    def connect(self) -> FakeSnowflakeConnection:
        connection = FakeSnowflakeConnection(self)
        self.connections.append(connection)
        return connection

    def next_rows(self) -> list[dict[str, Any]]:
        return self._rows.pop(0) if self._rows else []


BACKENDS = (
    BackendSpec(
        name="postgres",
        repository_class=object,
        database_factory=FakePostgresDatabase,
        row_adapter=lambda record: record,
    ),
    BackendSpec(
        name="snowflake",
        repository_class=object,
        database_factory=FakeSnowflakeDatabase,
        row_adapter=lambda record: {
            key.upper(): value
            for key, value in record.items()
        },
    ),
)


def test_postgres_record_adapter_converts_json_fields_to_jsonb() -> None:
    from psycopg.types.json import Jsonb

    from ai_governance.repositories.postgres._record_adapter import with_jsonb_fields

    adapted = with_jsonb_fields(
        {
            "payload_json": '{"enabled": true}',
            "empty_json": None,
        },
        "payload_json",
        "empty_json",
    )

    assert isinstance(adapted["payload_json"], Jsonb)
    assert adapted["empty_json"] is None


def _repository_class(
    backend: BackendSpec,
    spec: RepositorySpec,
) -> type:
    if backend.name == "postgres":
        return spec.postgres_class
    return spec.snowflake_class


def _dataset() -> Dataset:
    return Dataset(
        dataset_id="dataset-1",
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
        status=DatasetStatus.ACTIVE,
    )


def _prompt() -> Prompt:
    return Prompt(
        prompt_id="prompt-1",
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=("claim_text",),
        created_at=datetime(2026, 6, 25, tzinfo=UTC),
        created_by="governance-admin",
        status=PromptStatus.ACTIVE,
    )


def _model() -> Model:
    return Model(
        model_id="model-1",
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={"temperature": 0.0},
        cost={"input_per_1k": 0.01},
        latency=0.42,
        context_window=128000,
        creator="governance-admin",
        created_at=datetime(2026, 6, 25, tzinfo=UTC),
        status=ModelStatus.ACTIVE,
    )


def _evaluation_result() -> EvaluationResult:
    return EvaluationResult(
        evaluation_id="evaluation-1",
        execution_id="execution-1",
        evaluator_type="trulens",
        evaluator_version="1.0.0",
        metrics=[
            EvaluationMetric(
                metric_name="ANSWER_RELEVANCE",
                metric_value=0.95,
                explanation="Highly relevant",
            ),
            EvaluationMetric(
                metric_name="GROUNDEDNESS",
                metric_value=0.89,
                explanation="Well grounded",
            ),
        ],
        metadata={"model": "gpt-4o"},
    )


def _experiment() -> Experiment:
    return Experiment(
        experiment_id="experiment-1",
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
        status=ExperimentStatus.RUNNING,
    )


def _candidate() -> ExperimentCandidate:
    return ExperimentCandidate(
        candidate_id="candidate-1",
        experiment_id="experiment-1",
        name="Baseline",
        prompt_id="prompt-1",
        prompt_version="v1",
        model_id="model-1",
        model_version="2026-06-25",
        dataset_id="dataset-1",
        dataset_version="2026-06-26",
        evaluation_provider="TruLens",
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
        metadata={"tier": "baseline"},
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
    )


def _run() -> EvaluationRun:
    return EvaluationRun(
        run_id="run-1",
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        dataset_version="2026-06-26",
        evaluation_provider="TruLens",
        evaluation_result_id="evaluation-1",
        started_at=datetime(2026, 6, 26, tzinfo=UTC),
        completed_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
        status=EvaluationRunStatus.COMPLETED,
    )


def _leaderboard() -> Leaderboard:
    return Leaderboard(
        leaderboard_id="leaderboard-1",
        experiment_id="experiment-1",
        ranking_strategy="overall_score",
        generated_at=datetime(2026, 6, 26, tzinfo=UTC),
        entries=(
            LeaderboardEntry(
                rank=1,
                candidate_id="candidate-1",
                overall_score=0.94,
                metrics={"GROUNDEDNESS": 0.95},
                cost=0.02,
                latency=0.4,
                reason="Top candidate.",
            ),
        ),
    )


def _single_record_spec(
    name: str,
    postgres_class: type,
    snowflake_class: type,
    entity: Any,
    records: list[dict[str, Any]],
    id_method: str,
    id_args: tuple[Any, ...],
    one_methods: tuple[tuple[str, tuple[Any, ...]], ...] = (),
    list_methods: tuple[tuple[str, tuple[Any, ...]], ...] = (),
) -> RepositorySpec:
    return RepositorySpec(
        name=name,
        postgres_class=postgres_class,
        snowflake_class=snowflake_class,
        entity=entity,
        records=records,
        save_method="save",
        read_cases=(
            (id_method, id_args, [records], entity),
            *(
                (method_name, args, [records], entity)
                for method_name, args in one_methods
            ),
            *(
                (method_name, args, [records], [entity])
                for method_name, args in list_methods
            ),
        ),
        none_case=(id_method, id_args, [[]]),
    )


dataset = _dataset()
dataset_records = [
    DatasetPersistenceMapper.to_persistence_record(dataset)
]
prompt = _prompt()
prompt_records = [
    PromptPersistenceMapper.to_persistence_record(prompt)
]
model = _model()
model_records = [
    ModelPersistenceMapper.to_persistence_record(model)
]
evaluation_result = _evaluation_result()
evaluation_records = EvaluationPersistenceMapper.to_persistence_records(
    evaluation_result
)
experiment = _experiment()
experiment_records = [
    ExperimentPersistenceMapper.to_persistence_record(experiment)
]
candidate = _candidate()
candidate_records = [
    ExperimentCandidatePersistenceMapper.to_persistence_record(candidate)
]
run = _run()
run_records = [
    EvaluationRunPersistenceMapper.to_persistence_record(run)
]
leaderboard = _leaderboard()
leaderboard_record, leaderboard_entry_records = (
    LeaderboardPersistenceMapper.to_persistence_records(leaderboard)
)

REPOSITORY_SPECS = (
    _single_record_spec(
        "dataset",
        PostgresDatasetRepository,
        SnowflakeDatasetRepository,
        dataset,
        dataset_records,
        "find_by_id",
        (dataset.dataset_id,),
        one_methods=(
            ("find_by_name_and_version", (dataset.name, dataset.version)),
        ),
        list_methods=(
            ("find_by_name", (dataset.name,)),
            ("find_all", ()),
        ),
    ),
    _single_record_spec(
        "prompt",
        PostgresPromptRepository,
        SnowflakePromptRepository,
        prompt,
        prompt_records,
        "find_by_id",
        (prompt.prompt_id,),
        one_methods=(
            ("find_by_name_and_version", (prompt.name, prompt.version)),
        ),
        list_methods=(
            ("find_by_name", (prompt.name,)),
            ("find_all", ()),
        ),
    ),
    _single_record_spec(
        "model",
        PostgresModelRepository,
        SnowflakeModelRepository,
        model,
        model_records,
        "find_by_id",
        (model.model_id,),
        one_methods=(
            (
                "find_by_provider_name_and_version",
                (model.provider, model.model_name, model.version),
            ),
        ),
        list_methods=(
            ("find_by_logical_model", (model.provider, model.model_name)),
            ("find_all", ()),
        ),
    ),
    RepositorySpec(
        name="evaluation",
        postgres_class=PostgresEvaluationRepository,
        snowflake_class=SnowflakeEvaluationRepository,
        entity=evaluation_result,
        records=evaluation_records,
        save_method="save",
        read_cases=(
            (
                "find_by_evaluation_id",
                (evaluation_result.evaluation_id,),
                [evaluation_records],
                evaluation_result,
            ),
            (
                "find_by_execution_id",
                (evaluation_result.execution_id,),
                [evaluation_records],
                [evaluation_result],
            ),
        ),
        none_case=(
            "find_by_evaluation_id",
            (evaluation_result.evaluation_id,),
            [[]],
        ),
    ),
    _single_record_spec(
        "experiment",
        PostgresExperimentRepository,
        SnowflakeExperimentRepository,
        experiment,
        experiment_records,
        "find_by_id",
        (experiment.experiment_id,),
        one_methods=(
            ("find_by_name", (experiment.name,)),
        ),
        list_methods=(
            ("find_all", ()),
        ),
    ),
    _single_record_spec(
        "candidate",
        PostgresExperimentCandidateRepository,
        SnowflakeExperimentCandidateRepository,
        candidate,
        candidate_records,
        "find_by_id",
        (candidate.candidate_id,),
        list_methods=(
            ("find_by_experiment_id", (candidate.experiment_id,)),
            ("find_all", ()),
        ),
    ),
    _single_record_spec(
        "evaluation_run",
        PostgresEvaluationRunRepository,
        SnowflakeEvaluationRunRepository,
        run,
        run_records,
        "find_by_id",
        (run.run_id,),
        list_methods=(
            ("find_by_experiment_id", (run.experiment_id,)),
            ("find_by_candidate_id", (run.candidate_id,)),
            ("find_all", ()),
        ),
    ),
    RepositorySpec(
        name="leaderboard",
        postgres_class=PostgresLeaderboardRepository,
        snowflake_class=SnowflakeLeaderboardRepository,
        entity=leaderboard,
        records=[leaderboard_record, *leaderboard_entry_records],
        save_method="save",
        read_cases=(
            (
                "find_by_id",
                (leaderboard.leaderboard_id,),
                [[leaderboard_record], leaderboard_entry_records],
                leaderboard,
            ),
            (
                "find_by_experiment_id",
                (leaderboard.experiment_id,),
                [
                    [leaderboard_record],
                    [leaderboard_record],
                    leaderboard_entry_records,
                ],
                [leaderboard],
            ),
            (
                "find_all",
                (),
                [
                    [leaderboard_record],
                    [leaderboard_record],
                    leaderboard_entry_records,
                ],
                [leaderboard],
            ),
        ),
        none_case=("find_by_id", (leaderboard.leaderboard_id,), [[]]),
    ),
)


@pytest.mark.parametrize(
    "backend",
    BACKENDS,
    ids=lambda backend: backend.name,
)
@pytest.mark.parametrize(
    "spec",
    REPOSITORY_SPECS,
    ids=lambda spec: spec.name,
)
def test_sql_repositories_save_commits(
    backend: BackendSpec,
    spec: RepositorySpec,
) -> None:
    repository_class = _repository_class(backend, spec)
    database = backend.database_factory()
    repository = repository_class(database)

    getattr(repository, spec.save_method)(spec.entity)

    assert database.connections[-1].commits == 1
    assert database.connections[-1].rollbacks == 0


@pytest.mark.parametrize(
    "backend",
    BACKENDS,
    ids=lambda backend: backend.name,
)
@pytest.mark.parametrize(
    "spec",
    REPOSITORY_SPECS,
    ids=lambda spec: spec.name,
)
def test_sql_repositories_save_rolls_back_on_write_failure(
    backend: BackendSpec,
    spec: RepositorySpec,
) -> None:
    repository_class = _repository_class(backend, spec)
    database = backend.database_factory(fail_writes=True)
    repository = repository_class(database)

    with pytest.raises(RuntimeError):
        getattr(repository, spec.save_method)(spec.entity)

    assert database.connections[-1].commits == 0
    assert database.connections[-1].rollbacks == 1


@pytest.mark.parametrize(
    "backend",
    BACKENDS,
    ids=lambda backend: backend.name,
)
@pytest.mark.parametrize(
    "spec",
    REPOSITORY_SPECS,
    ids=lambda spec: spec.name,
)
def test_sql_repositories_read_domain_objects(
    backend: BackendSpec,
    spec: RepositorySpec,
) -> None:
    repository_class = _repository_class(backend, spec)

    for method_name, args, rows, expected in spec.read_cases:
        database = backend.database_factory(
            rows=[
                [backend.row_adapter(record) for record in result_rows]
                for result_rows in rows
            ]
        )
        repository = repository_class(database)

        assert getattr(repository, method_name)(*args) == expected


@pytest.mark.parametrize(
    "backend",
    BACKENDS,
    ids=lambda backend: backend.name,
)
@pytest.mark.parametrize(
    "spec",
    REPOSITORY_SPECS,
    ids=lambda spec: spec.name,
)
def test_sql_repositories_return_empty_results(
    backend: BackendSpec,
    spec: RepositorySpec,
) -> None:
    repository_class = _repository_class(backend, spec)
    method_name, args, rows = spec.none_case
    database = backend.database_factory(
        rows=[
            [backend.row_adapter(record) for record in result_rows]
            for result_rows in rows
        ]
    )
    repository = repository_class(database)

    result = getattr(repository, method_name)(*args)

    assert result in (None, [])
