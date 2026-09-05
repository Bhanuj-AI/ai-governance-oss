"""
Central application settings.

Repository backend selection is a control-plane configuration concern.
Each repository type can be configured independently via environment
variables.  The default for every repository is ``inmemory``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """
    Runtime configuration for AI Governance Control Plane.

    Repository backends
    -------------------
    Each repository type has a ``*_repository`` setting that selects the
    implementation (``inmemory``, ``sqlite``, or ``postgres``).  Durable
    backends require additional connection parameters.

    Policy administration
        AI_GOVERNANCE_POLICY_REPOSITORY          - inmemory | sqlite | postgres
        AI_GOVERNANCE_POLICY_SQLITE_PATH         - path to SQLite database file
        AI_GOVERNANCE_POLICY_POSTGRES_DSN        - PostgreSQL connection string

    Evaluation
        AI_GOVERNANCE_EVALUATION_REPOSITORY      - inmemory | sqlite | postgres
        AI_GOVERNANCE_EVALUATION_SQLITE_PATH     - path to SQLite database file
        AI_GOVERNANCE_EVALUATION_POSTGRES_DSN    - PostgreSQL connection string

    Experiment
        AI_GOVERNANCE_EXPERIMENT_REPOSITORY      - inmemory | sqlite | postgres
        AI_GOVERNANCE_EXPERIMENT_SQLITE_PATH     - path to SQLite database file
        AI_GOVERNANCE_EXPERIMENT_POSTGRES_DSN    - PostgreSQL connection string

    Experiment Candidate
        AI_GOVERNANCE_EXPERIMENT_CANDIDATE_REPOSITORY - inmemory | sqlite | postgres
        AI_GOVERNANCE_EXPERIMENT_CANDIDATE_SQLITE_PATH
        AI_GOVERNANCE_EXPERIMENT_CANDIDATE_POSTGRES_DSN

    Evaluation Run
        AI_GOVERNANCE_EVALUATION_RUN_REPOSITORY  - inmemory | sqlite | postgres
        AI_GOVERNANCE_EVALUATION_RUN_SQLITE_PATH
        AI_GOVERNANCE_EVALUATION_RUN_POSTGRES_DSN

    Leaderboard
        AI_GOVERNANCE_LEADERBOARD_REPOSITORY     - inmemory | sqlite | postgres
        AI_GOVERNANCE_LEADERBOARD_SQLITE_PATH
        AI_GOVERNANCE_LEADERBOARD_POSTGRES_DSN

    Prompt
        AI_GOVERNANCE_PROMPT_REPOSITORY          - inmemory | sqlite | postgres
        AI_GOVERNANCE_PROMPT_SQLITE_PATH         - path to SQLite database file
        AI_GOVERNANCE_PROMPT_POSTGRES_DSN        - PostgreSQL connection string

    Model
        AI_GOVERNANCE_MODEL_REPOSITORY           - inmemory | sqlite | postgres
        AI_GOVERNANCE_MODEL_SQLITE_PATH          - path to SQLite database file
        AI_GOVERNANCE_MODEL_POSTGRES_DSN         - PostgreSQL connection string

    Dataset
        AI_GOVERNANCE_DATASET_REPOSITORY         - inmemory | sqlite | postgres
        AI_GOVERNANCE_DATASET_SQLITE_PATH        - path to SQLite database file
        AI_GOVERNANCE_DATASET_POSTGRES_DSN       - PostgreSQL connection string

    Job
        AI_GOVERNANCE_JOB_REPOSITORY             - inmemory | sqlite | postgres
        AI_GOVERNANCE_JOB_SQLITE_PATH            - path to SQLite database file
        AI_GOVERNANCE_JOB_POSTGRES_DSN           - PostgreSQL connection string

    Governance Decision
        AI_GOVERNANCE_GOVERNANCE_DECISION_REPOSITORY - inmemory | sqlite | postgres
        AI_GOVERNANCE_GOVERNANCE_DECISION_SQLITE_PATH
        AI_GOVERNANCE_GOVERNANCE_DECISION_POSTGRES_DSN

    Ontology Sync Event
        AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_REPOSITORY - inmemory | sqlite | postgres
        AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_SQLITE_PATH
        AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_POSTGRES_DSN

    Ontology Graph
        AI_GOVERNANCE_ONTOLOGY_REPOSITORY        - inmemory | sqlite | postgres
        AI_GOVERNANCE_ONTOLOGY_SQLITE_PATH       - path to SQLite database file
        AI_GOVERNANCE_ONTOLOGY_POSTGRES_DSN      - PostgreSQL connection string

    Agent Execution Trace
        AI_GOVERNANCE_AGENT_EXECUTION_REPOSITORY - inmemory | sqlite | postgres
        AI_GOVERNANCE_AGENT_EXECUTION_SQLITE_PATH
        AI_GOVERNANCE_AGENT_EXECUTION_POSTGRES_DSN
    """

    # Policy administration
    policy_repository: str
    policy_sqlite_path: str | None
    policy_postgres_dsn: str | None

    # Evaluation
    evaluation_repository: str
    evaluation_sqlite_path: str | None
    evaluation_postgres_dsn: str | None

    # Experiment
    experiment_repository: str
    experiment_sqlite_path: str | None
    experiment_postgres_dsn: str | None

    # Experiment Candidate
    experiment_candidate_repository: str
    experiment_candidate_sqlite_path: str | None
    experiment_candidate_postgres_dsn: str | None

    # Evaluation Run
    evaluation_run_repository: str
    evaluation_run_sqlite_path: str | None
    evaluation_run_postgres_dsn: str | None

    # Leaderboard
    leaderboard_repository: str
    leaderboard_sqlite_path: str | None
    leaderboard_postgres_dsn: str | None

    # Prompt
    prompt_repository: str
    prompt_sqlite_path: str | None
    prompt_postgres_dsn: str | None

    # Model
    model_repository: str
    model_sqlite_path: str | None
    model_postgres_dsn: str | None

    # Dataset
    dataset_repository: str
    dataset_sqlite_path: str | None
    dataset_postgres_dsn: str | None

    # Job
    job_repository: str
    job_sqlite_path: str | None
    job_postgres_dsn: str | None

    # Governance Decision
    governance_decision_repository: str
    governance_decision_sqlite_path: str | None
    governance_decision_postgres_dsn: str | None

    # Ontology Sync Event
    ontology_sync_event_repository: str
    ontology_sync_event_sqlite_path: str | None
    ontology_sync_event_postgres_dsn: str | None

    # Ontology Graph
    ontology_repository: str
    ontology_sqlite_path: str | None
    ontology_postgres_dsn: str | None

    # Agent Execution Trace
    agent_execution_repository: str
    agent_execution_sqlite_path: str | None
    agent_execution_postgres_dsn: str | None

    # Authentication
    auth_mode: str = "development"
    oidc_issuer: str | None = None
    oidc_jwks_refresh_seconds: int = 300

    # Bootstrap administrator (Keycloak mode)
    bootstrap_admin_sub: str | None = None
    bootstrap_admin_name: str | None = None

    # Replay Management
    replay_repository: str = "inmemory"
    replay_sqlite_path: str | None = None
    replay_postgres_dsn: str | None = None
    replay_execution_catalog_backend: str = "inmemory"
    replay_execution_catalog_sqlite_path: str | None = None


def _load_str(env_var: str, default: str = "inmemory") -> str:
    """Load a string setting, normalising to lowercase."""
    value = os.getenv(env_var, default)
    return value.strip().lower()


def _load_path(env_var: str) -> str | None:
    """Load an optional path setting."""
    value = os.getenv(env_var)
    return value.strip() if value else None


def load_settings() -> Settings:
    """
    Resolve application settings from environment variables.

    All repository backends default to ``inmemory`` unless explicitly
    configured.  Durable backends require their respective connection
    parameters; factories will fail fast if they are missing.
    """

    return Settings(
        # Policy administration
        policy_repository=_load_str("AI_GOVERNANCE_POLICY_REPOSITORY"),
        policy_sqlite_path=_load_path("AI_GOVERNANCE_POLICY_SQLITE_PATH"),
        policy_postgres_dsn=_load_path("AI_GOVERNANCE_POLICY_POSTGRES_DSN"),
        # Evaluation
        evaluation_repository=_load_str("AI_GOVERNANCE_EVALUATION_REPOSITORY"),
        evaluation_sqlite_path=_load_path("AI_GOVERNANCE_EVALUATION_SQLITE_PATH"),
        evaluation_postgres_dsn=_load_path("AI_GOVERNANCE_EVALUATION_POSTGRES_DSN"),
        # Experiment
        experiment_repository=_load_str("AI_GOVERNANCE_EXPERIMENT_REPOSITORY"),
        experiment_sqlite_path=_load_path("AI_GOVERNANCE_EXPERIMENT_SQLITE_PATH"),
        experiment_postgres_dsn=_load_path("AI_GOVERNANCE_EXPERIMENT_POSTGRES_DSN"),
        # Experiment Candidate
        experiment_candidate_repository=_load_str(
            "AI_GOVERNANCE_EXPERIMENT_CANDIDATE_REPOSITORY"
        ),
        experiment_candidate_sqlite_path=_load_path(
            "AI_GOVERNANCE_EXPERIMENT_CANDIDATE_SQLITE_PATH"
        ),
        experiment_candidate_postgres_dsn=_load_path(
            "AI_GOVERNANCE_EXPERIMENT_CANDIDATE_POSTGRES_DSN"
        ),
        # Evaluation Run
        evaluation_run_repository=_load_str("AI_GOVERNANCE_EVALUATION_RUN_REPOSITORY"),
        evaluation_run_sqlite_path=_load_path("AI_GOVERNANCE_EVALUATION_RUN_SQLITE_PATH"),
        evaluation_run_postgres_dsn=_load_path("AI_GOVERNANCE_EVALUATION_RUN_POSTGRES_DSN"),
        # Leaderboard
        leaderboard_repository=_load_str("AI_GOVERNANCE_LEADERBOARD_REPOSITORY"),
        leaderboard_sqlite_path=_load_path("AI_GOVERNANCE_LEADERBOARD_SQLITE_PATH"),
        leaderboard_postgres_dsn=_load_path("AI_GOVERNANCE_LEADERBOARD_POSTGRES_DSN"),
        # Prompt
        prompt_repository=_load_str("AI_GOVERNANCE_PROMPT_REPOSITORY"),
        prompt_sqlite_path=_load_path("AI_GOVERNANCE_PROMPT_SQLITE_PATH"),
        prompt_postgres_dsn=_load_path("AI_GOVERNANCE_PROMPT_POSTGRES_DSN"),
        # Model
        model_repository=_load_str("AI_GOVERNANCE_MODEL_REPOSITORY"),
        model_sqlite_path=_load_path("AI_GOVERNANCE_MODEL_SQLITE_PATH"),
        model_postgres_dsn=_load_path("AI_GOVERNANCE_MODEL_POSTGRES_DSN"),
        # Dataset
        dataset_repository=_load_str("AI_GOVERNANCE_DATASET_REPOSITORY"),
        dataset_sqlite_path=_load_path("AI_GOVERNANCE_DATASET_SQLITE_PATH"),
        dataset_postgres_dsn=_load_path("AI_GOVERNANCE_DATASET_POSTGRES_DSN"),
        # Job
        job_repository=_load_str("AI_GOVERNANCE_JOB_REPOSITORY"),
        job_sqlite_path=_load_path("AI_GOVERNANCE_JOB_SQLITE_PATH"),
        job_postgres_dsn=_load_path("AI_GOVERNANCE_JOB_POSTGRES_DSN"),
        # Governance Decision
        governance_decision_repository=_load_str(
            "AI_GOVERNANCE_GOVERNANCE_DECISION_REPOSITORY"
        ),
        governance_decision_sqlite_path=_load_path(
            "AI_GOVERNANCE_GOVERNANCE_DECISION_SQLITE_PATH"
        ),
        governance_decision_postgres_dsn=_load_path(
            "AI_GOVERNANCE_GOVERNANCE_DECISION_POSTGRES_DSN"
        ),
        # Ontology Sync Event
        ontology_sync_event_repository=_load_str(
            "AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_REPOSITORY"
        ),
        ontology_sync_event_sqlite_path=_load_path(
            "AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_SQLITE_PATH"
        ),
        ontology_sync_event_postgres_dsn=_load_path(
            "AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_POSTGRES_DSN"
        ),
        # Ontology Graph
        ontology_repository=_load_str("AI_GOVERNANCE_ONTOLOGY_REPOSITORY"),
        ontology_sqlite_path=_load_path("AI_GOVERNANCE_ONTOLOGY_SQLITE_PATH"),
        ontology_postgres_dsn=_load_path("AI_GOVERNANCE_ONTOLOGY_POSTGRES_DSN"),
        # Agent Execution Trace
        agent_execution_repository=_load_str(
            "AI_GOVERNANCE_AGENT_EXECUTION_REPOSITORY", "inmemory"
        ),
        agent_execution_sqlite_path=_load_path(
            "AI_GOVERNANCE_AGENT_EXECUTION_SQLITE_PATH"
        ),
        agent_execution_postgres_dsn=_load_path(
            "AI_GOVERNANCE_AGENT_EXECUTION_POSTGRES_DSN"
        ),
        # Authentication
        auth_mode=_load_str("AI_GOVERNANCE_AUTH_MODE", "development"),
        oidc_issuer=_load_path("AI_GOVERNANCE_OIDC_ISSUER"),
        oidc_jwks_refresh_seconds=int(
            os.getenv("AI_GOVERNANCE_OIDC_JWKS_REFRESH_SECONDS", "300")
        ),
        # Bootstrap administrator (Keycloak mode)
        bootstrap_admin_sub=_load_path("AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB"),
        bootstrap_admin_name=_load_path("AI_GOVERNANCE_BOOTSTRAP_ADMIN_NAME"),
        # Replay Management
        replay_repository=_load_str("AI_GOVERNANCE_REPLAY_REPOSITORY"),
        replay_sqlite_path=_load_path("AI_GOVERNANCE_REPLAY_SQLITE_PATH"),
        replay_postgres_dsn=_load_path("AI_GOVERNANCE_REPLAY_POSTGRES_DSN"),
        replay_execution_catalog_backend=_load_str(
            "AI_GOVERNANCE_REPLAY_EXECUTION_CATALOG_BACKEND", "inmemory"
        ),
        replay_execution_catalog_sqlite_path=_load_path(
            "AI_GOVERNANCE_REPLAY_EXECUTION_CATALOG_SQLITE_PATH"
        ),
    )
