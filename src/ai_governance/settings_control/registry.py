from __future__ import annotations

import json
import re
from types import MappingProxyType
from typing import Any

from ai_governance.version import __version__

from .domain import SettingCategory as C
from .domain import SettingDefinition, SettingScope, SettingValidationError
from .domain import SettingValueType as T


def _range(minimum: float, maximum: float):
    def validate(value: Any) -> None:
        if not minimum <= value <= maximum:
            raise SettingValidationError(
                f"Value must be between {minimum:g} and {maximum:g}."
            )

    return validate


def _non_empty(value: Any) -> None:
    if not str(value).strip():
        raise SettingValidationError("Value must not be blank.")


def _synthesizer_pricing(value: Any) -> None:
    if not isinstance(value, dict):
        raise SettingValidationError("Expected a model-to-pricing JSON object.")
    for model, rates in value.items():
        if (
            not isinstance(model, str)
            or not model.strip()
            or not isinstance(rates, dict)
        ):
            raise SettingValidationError(
                "Each pricing entry requires a model name and rate object."
            )
        for key in ("input", "cached_input", "output"):
            rate = rates.get(key)
            if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate < 0:
                raise SettingValidationError(
                    f"Pricing for '{model}' must include a non-negative '{key}' rate."
                )


def _definition(
    key: str,
    category: C,
    name: str,
    description: str,
    value_type: T,
    default: Any,
    *,
    mutable: bool = True,
    env: str | None = None,
    restart: bool = False,
    validator=None,
    enum: tuple[str, ...] = (),
    sensitive: bool = False,
    scopes: tuple[SettingScope, ...] | None = None,
    runtime_applied: bool = False,
) -> SettingDefinition:
    return SettingDefinition(
        key,
        category,
        name,
        description,
        value_type,
        default,
        mutable,
        sensitive,
        restart,
        env,
        validator,
        enum,
        scopes
        if scopes is not None
        else (
            (
                SettingScope.SYSTEM,
                SettingScope.ORGANIZATION,
                SettingScope.PROJECT,
            )
            if mutable
            else (SettingScope.SYSTEM,)
        ),
        runtime_applied,
    )


_DEFINITIONS = (
    _definition(
        "general.instance_name",
        C.GENERAL,
        "Instance Name",
        "Human-readable AI Governance Control Plane instance name.",
        T.STRING,
        "AI Governance Control Plane",
        env="AI_GOVERNANCE_INSTANCE_NAME",
        validator=_non_empty,
        runtime_applied=True,
    ),
    _definition(
        "general.environment",
        C.GENERAL,
        "Environment",
        "Deployment environment.",
        T.ENUM,
        "local",
        mutable=False,
        env="AI_GOVERNANCE_ENV",
        restart=True,
        enum=("local", "development", "staging", "production"),
    ),
    _definition(
        "general.version",
        C.GENERAL,
        "Version",
        "Installed AI Governance Control Plane release.",
        T.STRING,
        __version__,
        mutable=False,
    ),
    _definition(
        "general.build",
        C.GENERAL,
        "Build",
        "Build identifier.",
        T.STRING,
        "development",
        mutable=False,
        env="AI_GOVERNANCE_BUILD_ID",
        restart=True,
    ),
    _definition(
        "general.timezone",
        C.GENERAL,
        "Timezone",
        "Display timezone.",
        T.STRING,
        "UTC",
        env="AI_GOVERNANCE_TIMEZONE",
        validator=_non_empty,
        runtime_applied=True,
    ),
    _definition(
        "repositories.active_backend",
        C.REPOSITORIES,
        "Active Backend",
        "Primary repository backend.",
        T.ENUM,
        "inmemory",
        mutable=False,
        env="AI_GOVERNANCE_POLICY_REPOSITORY",
        restart=True,
        enum=("inmemory", "sqlite", "postgres"),
    ),
    _definition(
        "repositories.settings_backend",
        C.REPOSITORIES,
        "Settings Backend",
        "Runtime settings repository backend.",
        T.ENUM,
        "inmemory",
        mutable=False,
        env="AI_GOVERNANCE_SETTINGS_REPOSITORY",
        restart=True,
        enum=("inmemory", "sqlite", "postgres"),
    ),
    _definition(
        "repositories.connection_status",
        C.REPOSITORIES,
        "Connection Status",
        "Settings repository connection status.",
        T.ENUM,
        "connected",
        mutable=False,
        enum=("connected", "disconnected"),
    ),
    _definition(
        "repositories.migration_status",
        C.REPOSITORIES,
        "Migration Status",
        "Database migration status.",
        T.ENUM,
        "current",
        mutable=False,
        enum=("current", "pending", "unknown"),
    ),
    _definition(
        "jobs.worker_concurrency",
        C.JOBS,
        "Worker Concurrency",
        "Maximum concurrent job workers.",
        T.INTEGER,
        4,
        env="AI_GOVERNANCE_JOB_WORKER_CONCURRENCY",
        validator=_range(1, 128),
        runtime_applied=True,
    ),
    _definition(
        "jobs.retry_attempts",
        C.JOBS,
        "Retry Attempts",
        "Default job retry attempts.",
        T.INTEGER,
        3,
        env="AI_GOVERNANCE_JOB_RETRY_ATTEMPTS",
        validator=_range(1, 10),
        runtime_applied=True,
    ),
    _definition(
        "jobs.retry_delay",
        C.JOBS,
        "Retry Delay",
        "Delay between job retries.",
        T.DURATION,
        "1ms",
        env="AI_GOVERNANCE_JOB_RETRY_DELAY",
        runtime_applied=True,
    ),
    _definition(
        "jobs.queue_size",
        C.JOBS,
        "Queue Size",
        "Maximum queued jobs.",
        T.INTEGER,
        1000,
        env="AI_GOVERNANCE_JOB_QUEUE_SIZE",
        validator=_range(1, 100000),
        runtime_applied=True,
    ),
    _definition(
        "jobs.retention",
        C.JOBS,
        "Retention",
        "Completed-job retention period.",
        T.DURATION,
        "30d",
        env="AI_GOVERNANCE_JOB_RETENTION",
        runtime_applied=True,
    ),
    _definition(
        "governance.decision_retention",
        C.GOVERNANCE,
        "Decision Retention",
        "Governance decision retention period.",
        T.DURATION,
        "365d",
        env="AI_GOVERNANCE_DECISION_RETENTION",
        runtime_applied=True,
    ),
    _definition(
        "governance.replay_retention",
        C.GOVERNANCE,
        "Replay Retention",
        "Workflow replay retention period.",
        T.DURATION,
        "90d",
        env="AI_GOVERNANCE_REPLAY_RETENTION",
        runtime_applied=True,
    ),
    _definition(
        "replay.retention",
        C.GOVERNANCE,
        "Replay Retention",
        "Retention period for archived Replay Management records.",
        T.DURATION,
        "90d",
        env="AI_GOVERNANCE_REPLAY_RETENTION",
        runtime_applied=True,
    ),
    _definition(
        "replay.max_concurrent_jobs",
        C.GOVERNANCE,
        "Replay Maximum Concurrent Jobs",
        "Maximum replay execution jobs across the platform.",
        T.INTEGER,
        4,
        env="AI_GOVERNANCE_REPLAY_MAX_CONCURRENT_JOBS",
        validator=_range(1, 128),
        runtime_applied=True,
    ),
    _definition(
        "replay.max_concurrent_jobs_per_project",
        C.GOVERNANCE,
        "Replay Maximum Concurrent Jobs Per Project",
        "Maximum replay execution jobs within one project.",
        T.INTEGER,
        2,
        env="AI_GOVERNANCE_REPLAY_MAX_CONCURRENT_JOBS_PER_PROJECT",
        validator=_range(1, 128),
        runtime_applied=True,
    ),
    _definition(
        "replay.max_attempts",
        C.GOVERNANCE,
        "Replay Maximum Attempts",
        "Maximum job attempts for one replay execution.",
        T.INTEGER,
        3,
        env="AI_GOVERNANCE_REPLAY_MAX_ATTEMPTS",
        validator=_range(1, 10),
        runtime_applied=True,
    ),
    _definition(
        "replay.default_baseline_strategy",
        C.GOVERNANCE,
        "Replay Default Baseline Strategy",
        "Baseline strategy used for replay evaluation when none is specified.",
        T.ENUM,
        "LATEST_COMPATIBLE",
        env="AI_GOVERNANCE_REPLAY_DEFAULT_BASELINE_STRATEGY",
        enum=("EXPLICIT", "LATEST_COMPATIBLE", "SOURCE_PRIMARY"),
        runtime_applied=True,
    ),
    _definition(
        "replay.evaluation_max_attempts",
        C.GOVERNANCE,
        "Replay Evaluation Maximum Attempts",
        "Maximum attempts for a replay evaluation job.",
        T.INTEGER,
        3,
        env="AI_GOVERNANCE_REPLAY_EVALUATION_MAX_ATTEMPTS",
        validator=_range(1, 10),
        runtime_applied=True,
    ),
    _definition(
        "replay.drift_threshold_policy",
        C.GOVERNANCE,
        "Replay Drift Threshold Policy",
        "Resolved drift policy retained with replay evidence.",
        T.JSON,
        {"policy": "governance-default-v1"},
        env="AI_GOVERNANCE_REPLAY_DRIFT_THRESHOLD_POLICY",
        runtime_applied=True,
    ),
    _definition(
        "replay.result_retention",
        C.GOVERNANCE,
        "Replay Result Retention",
        "Retention period for immutable replay result evidence.",
        T.DURATION,
        "90d",
        env="AI_GOVERNANCE_REPLAY_RESULT_RETENTION",
        runtime_applied=True,
    ),
    _definition(
        "intelligence.replay_history_limit",
        C.GOVERNANCE,
        "Replay Advisor Historical Job Limit",
        "Maximum terminal Replay jobs supplied to the Intelligence Replay Advisor.",
        T.INTEGER,
        3,
        env="AI_GOVERNANCE_INTELLIGENCE_REPLAY_HISTORY_LIMIT",
        validator=_range(1, 20),
        runtime_applied=True,
    ),
    _definition(
        "intelligence.synthesizer_provider",
        C.GOVERNANCE,
        "Intelligence Synthesizer Provider",
        "Configured governed provider used to synthesize Intelligence evidence.",
        T.STRING,
        "openai",
        env="AI_GOVERNANCE_INTELLIGENCE_SYNTHESIZER_PROVIDER",
        validator=_non_empty,
        runtime_applied=True,
    ),
    _definition(
        "intelligence.synthesizer_model",
        C.GOVERNANCE,
        "Intelligence Synthesizer Model",
        "Model selected for evidence-grounded Intelligence synthesis.",
        T.STRING,
        "gpt-4.1-mini",
        env="AI_GOVERNANCE_INTELLIGENCE_SYNTHESIZER_MODEL",
        validator=_non_empty,
        runtime_applied=True,
    ),
    _definition(
        "intelligence.synthesizer_pricing",
        C.GOVERNANCE,
        "Intelligence Synthesizer Pricing",
        "Estimated USD rates per million tokens for each Intelligence synthesis model.",
        T.JSON,
        {
            "gpt-4.1-mini": {"input": 0.40, "cached_input": 0.10, "output": 1.60},
            "gpt-5.6-luna": {"input": 1.00, "cached_input": 0.10, "output": 6.00},
            "gpt-5.6-terra": {"input": 2.50, "cached_input": 0.25, "output": 15.00},
            "gpt-5.6-sol": {"input": 5.00, "cached_input": 0.50, "output": 30.00},
        },
        env="AI_GOVERNANCE_INTELLIGENCE_SYNTHESIZER_PRICING",
        validator=_synthesizer_pricing,
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.enabled",
        C.GOVERNANCE,
        "Enterprise Recommendations Enabled",
        "Enable read-only Enterprise recommendation collection.",
        T.BOOLEAN,
        True,
        env="AI_GOVERNANCE_ENTERPRISE_RECOMMENDATIONS_ENABLED",
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.default_limit",
        C.GOVERNANCE,
        "Enterprise Recommendations Default Limit",
        "Default maximum number of recommendations returned.",
        T.INTEGER,
        20,
        validator=_range(1, 100),
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.include_informational",
        C.GOVERNANCE,
        "Enterprise Recommendations Include Informational",
        "Include informational recommendations by default.",
        T.BOOLEAN,
        False,
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.narrative_enabled",
        C.GOVERNANCE,
        "Enterprise Recommendation Narrative Enabled",
        "Permit provider-backed wording after deterministic recommendation collection.",
        T.BOOLEAN,
        False,
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.max_narrative_items",
        C.GOVERNANCE,
        "Enterprise Recommendation Narrative Limit",
        "Maximum recommendations eligible for narrative synthesis per request.",
        T.INTEGER,
        5,
        validator=_range(0, 20),
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.operational_window_days",
        C.GOVERNANCE,
        "Enterprise Operational Summary Window",
        "Default requested operational summary window in days.",
        T.INTEGER,
        7,
        validator=_range(1, 30),
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.governance_weight",
        C.GOVERNANCE,
        "Governance Recommendation Weight",
        "Deterministic relative priority weight for governance recommendations.",
        T.FLOAT,
        1.0,
        validator=_range(0, 10),
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.replay_weight",
        C.GOVERNANCE,
        "Replay Recommendation Weight",
        "Deterministic relative priority weight for replay recommendations.",
        T.FLOAT,
        1.0,
        validator=_range(0, 10),
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.experiment_weight",
        C.GOVERNANCE,
        "Experiment Recommendation Weight",
        "Deterministic relative priority weight for experiment recommendations.",
        T.FLOAT,
        1.0,
        validator=_range(0, 10),
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.root_cause_weight",
        C.GOVERNANCE,
        "Root-cause Recommendation Weight",
        "Deterministic relative priority weight for root-cause recommendations.",
        T.FLOAT,
        1.0,
        validator=_range(0, 10),
        runtime_applied=True,
    ),
    _definition(
        "enterprise.recommendations.operational_weight",
        C.GOVERNANCE,
        "Operational Recommendation Weight",
        "Deterministic relative priority weight for operational recommendations.",
        T.FLOAT,
        1.0,
        validator=_range(0, 10),
        runtime_applied=True,
    ),
    _definition(
        "governance.default_policy_version_behavior",
        C.GOVERNANCE,
        "Default Policy Version",
        "Policy version selection behavior.",
        T.ENUM,
        "active",
        env="AI_GOVERNANCE_DEFAULT_POLICY_VERSION_BEHAVIOR",
        enum=("active", "latest", "explicit"),
        runtime_applied=True,
    ),
    _definition(
        "evaluation.default_provider",
        C.EVALUATION,
        "Default Provider",
        "Default evaluation provider.",
        T.STRING,
        "mock",
        env="AI_GOVERNANCE_DEFAULT_EVALUATION_PROVIDER",
        validator=_non_empty,
        runtime_applied=True,
    ),
    _definition(
        "evaluation.pass_threshold",
        C.EVALUATION,
        "Pass Threshold",
        "Default evaluation pass threshold.",
        T.FLOAT,
        0.8,
        env="AI_GOVERNANCE_EVALUATION_PASS_THRESHOLD",
        validator=_range(0, 1),
        runtime_applied=True,
    ),
    _definition(
        "evaluation.thresholds",
        C.EVALUATION,
        "Metric Thresholds",
        "Per-metric evaluation thresholds.",
        T.JSON,
        {},
        env="AI_GOVERNANCE_EVALUATION_THRESHOLDS",
        runtime_applied=True,
    ),
    _definition(
        "evaluation.retention",
        C.EVALUATION,
        "Retention",
        "Evaluation result retention period.",
        T.DURATION,
        "180d",
        env="AI_GOVERNANCE_EVALUATION_RETENTION",
        runtime_applied=True,
    ),
    _definition(
        "ontology.projection_interval",
        C.ONTOLOGY,
        "Projection Interval",
        "Ontology projection interval.",
        T.DURATION,
        "30s",
        env="AI_GOVERNANCE_ONTOLOGY_PROJECTION_INTERVAL",
        runtime_applied=True,
    ),
    _definition(
        "ontology.reconciliation_interval",
        C.ONTOLOGY,
        "Reconciliation Interval",
        "Ontology reconciliation interval.",
        T.DURATION,
        "5m",
        env="AI_GOVERNANCE_ONTOLOGY_RECONCILIATION_INTERVAL",
        runtime_applied=True,
    ),
    _definition(
        "ontology.neo4j_endpoint",
        C.ONTOLOGY,
        "Neo4j Endpoint",
        "Configured Neo4j endpoint.",
        T.STRING,
        "not configured",
        mutable=False,
        env="AI_GOVERNANCE_GRAPH_URI",
        restart=True,
    ),
    _definition(
        "ontology.connection_health",
        C.ONTOLOGY,
        "Connection Health",
        "Neo4j connection health.",
        T.ENUM,
        "unknown",
        mutable=False,
        enum=("connected", "disconnected", "unknown"),
    ),
    _definition(
        "audit.retention",
        C.AUDIT,
        "Retention",
        "Audit record retention period.",
        T.DURATION,
        "365d",
        env="AI_GOVERNANCE_AUDIT_RETENTION",
        runtime_applied=True,
    ),
    _definition(
        "audit.interrupted_timeout",
        C.AUDIT,
        "Interrupted Timeout",
        "Timeout before an operation is considered interrupted.",
        T.DURATION,
        "15m",
        env="AI_GOVERNANCE_AUDIT_INTERRUPTED_TIMEOUT",
        runtime_applied=True,
    ),
    _definition(
        "audit.backend",
        C.AUDIT,
        "Backend",
        "Audit persistence backend.",
        T.ENUM,
        "sqlite",
        mutable=False,
        env="AI_GOVERNANCE_MCP_AUDIT_BACKEND",
        restart=True,
        enum=("memory", "sqlite", "postgres"),
    ),
    _definition(
        "mcp.dry_run_default",
        C.MCP,
        "Dry-run Default",
        "Default MCP controlled writes to dry-run.",
        T.BOOLEAN,
        False,
        env="AI_GOVERNANCE_MCP_DRY_RUN_DEFAULT",
        runtime_applied=True,
    ),
    _definition(
        "mcp.audit_required",
        C.MCP,
        "Audit Required",
        "Require audit logging for MCP writes.",
        T.BOOLEAN,
        True,
        env="AI_GOVERNANCE_MCP_AUDIT_REQUIRED",
        runtime_applied=True,
    ),
    _definition(
        "mcp.idempotency_expiry",
        C.MCP,
        "Idempotency Expiry",
        "MCP idempotency-key retention.",
        T.DURATION,
        "24h",
        env="AI_GOVERNANCE_MCP_IDEMPOTENCY_EXPIRY",
        runtime_applied=True,
    ),
    _definition(
        "integrations.openai",
        C.INTEGRATIONS,
        "OpenAI",
        "OpenAI integration status.",
        T.ENUM,
        "disconnected",
        mutable=False,
        env="OPENAI_API_KEY",
        enum=("connected", "disconnected"),
        sensitive=True,
    ),
    _definition(
        "integrations.neo4j",
        C.INTEGRATIONS,
        "Neo4j",
        "Neo4j integration status.",
        T.ENUM,
        "disconnected",
        mutable=False,
        env="AI_GOVERNANCE_GRAPH_URI",
        enum=("connected", "disconnected"),
    ),
    _definition(
        "integrations.msteams",
        C.INTEGRATIONS,
        "MS Teams",
        "MS Teams integration status.",
        T.ENUM,
        "disconnected",
        mutable=False,
        env="AI_GOVERNANCE_MSTEAMS_WEBHOOK_URL",
        enum=("connected", "disconnected"),
        sensitive=True,
    ),
    _definition(
        "integrations.webhook",
        C.INTEGRATIONS,
        "Webhook",
        "Webhook integration status.",
        T.ENUM,
        "disconnected",
        mutable=False,
        env="AI_GOVERNANCE_WEBHOOK_URL",
        enum=("connected", "disconnected"),
        sensitive=True,
    ),
    _definition(
        "system.version",
        C.SYSTEM,
        "Version",
        "Installed AI Governance Control Plane release.",
        T.STRING,
        __version__,
        mutable=False,
    ),
    _definition(
        "system.commit_sha",
        C.SYSTEM,
        "Commit SHA",
        "Source revision.",
        T.STRING,
        "unknown",
        mutable=False,
        env="AI_GOVERNANCE_COMMIT_SHA",
        restart=True,
    ),
    _definition(
        "system.build_date",
        C.SYSTEM,
        "Build Date",
        "Build timestamp.",
        T.STRING,
        "unknown",
        mutable=False,
        env="AI_GOVERNANCE_BUILD_DATE",
        restart=True,
    ),
    _definition(
        "system.python_version",
        C.SYSTEM,
        "Python Version",
        "Python runtime version.",
        T.STRING,
        "runtime",
        mutable=False,
    ),
)

_SETTINGS = {item.key: item for item in _DEFINITIONS}
SETTINGS_REGISTRY = MappingProxyType(_SETTINGS)

def register_extension_definitions(definitions) -> None:
    """Register validated plugin settings before configuration services run."""
    for definition in definitions:
        if not isinstance(definition, SettingDefinition):
            raise TypeError("Plugin settings must be SettingDefinition instances.")
        if definition.key in _SETTINGS:
            raise ValueError(f"Setting '{definition.key}' is already registered.")
        _SETTINGS[definition.key] = definition


def parse_value(definition: SettingDefinition, value: Any) -> Any:
    try:
        if definition.value_type is T.STRING:
            parsed = str(value)
        elif definition.value_type is T.INTEGER:
            parsed = int(value)
        elif definition.value_type is T.FLOAT:
            parsed = float(value)
        elif definition.value_type is T.BOOLEAN:
            if isinstance(value, bool):
                parsed = value
            elif str(value).strip().lower() in {"1", "true", "yes", "on"}:
                parsed = True
            elif str(value).strip().lower() in {"0", "false", "no", "off"}:
                parsed = False
            else:
                raise ValueError("expected a boolean")
        elif definition.value_type is T.JSON:
            parsed = json.loads(value) if isinstance(value, str) else value
        elif definition.value_type is T.DURATION:
            parsed = str(value).strip().lower()
            if not re.fullmatch(r"[1-9][0-9]*(ms|s|m|h|d|w)", parsed):
                raise ValueError("expected a duration such as 30s, 5m, 24h, or 30d")
        elif definition.value_type is T.ENUM:
            parsed = str(value).strip().lower()
            if parsed not in definition.enum_values:
                raise ValueError(
                    f"expected one of: {', '.join(definition.enum_values)}"
                )
        else:
            parsed = value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SettingValidationError(
            f"Invalid value for {definition.key}: {exc}"
        ) from exc
    if definition.validator:
        definition.validator(parsed)
    return parsed
