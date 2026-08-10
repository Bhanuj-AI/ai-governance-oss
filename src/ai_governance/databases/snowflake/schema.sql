CREATE TABLE IF NOT EXISTS agent_evaluation (

    evaluation_id VARCHAR NOT NULL,
    execution_id VARCHAR NOT NULL,

    evaluator_type VARCHAR NOT NULL,
    evaluator_version VARCHAR NOT NULL,

    metric_name VARCHAR NOT NULL,
    metric_score FLOAT NOT NULL,

    metadata_json VARIANT,
    provider_metadata_json VARIANT,
    provider_descriptor_snapshot_json VARIANT,
    artifacts_json VARIANT,
    created_at TIMESTAMP_TZ,
    explanation VARCHAR,

    PRIMARY KEY (
        evaluation_id,
        metric_name
    )
);

CREATE TABLE IF NOT EXISTS prompt_registry (

    prompt_id VARCHAR NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,
    version VARCHAR NOT NULL,

    template VARCHAR,
    variables_json VARIANT NOT NULL,

    created_at TIMESTAMP_TZ NOT NULL,
    created_by VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    provenance VARCHAR NOT NULL DEFAULT 'MANAGED',
    source_system VARCHAR,
    source_reference VARCHAR,
    content_hash VARCHAR,
    content_available BOOLEAN NOT NULL DEFAULT TRUE,
    tenant_id VARCHAR NOT NULL DEFAULT 'org_default',
    organization_id VARCHAR NOT NULL DEFAULT 'org_default',
    project_id VARCHAR NOT NULL DEFAULT 'project_default',

    UNIQUE (
        name,
        version
    )
);

CREATE TABLE IF NOT EXISTS model_registry (

    model_id VARCHAR NOT NULL PRIMARY KEY,
    provider VARCHAR NOT NULL,
    model_name VARCHAR NOT NULL,
    version VARCHAR NOT NULL,

    parameters_json VARIANT NOT NULL,
    cost_json VARIANT,
    latency FLOAT,
    context_window NUMBER NOT NULL,

    creator VARCHAR NOT NULL,
    created_at TIMESTAMP_TZ NOT NULL,
    status VARCHAR NOT NULL,
    provenance VARCHAR NOT NULL DEFAULT 'MANAGED',
    source_system VARCHAR,
    source_reference VARCHAR,
    tenant_id VARCHAR NOT NULL DEFAULT 'org_default',
    organization_id VARCHAR NOT NULL DEFAULT 'org_default',
    project_id VARCHAR NOT NULL DEFAULT 'project_default',

    UNIQUE (
        provider,
        model_name,
        version
    )
);

CREATE TABLE IF NOT EXISTS dataset_registry (

    dataset_id VARCHAR NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,
    version VARCHAR NOT NULL,

    description VARCHAR NOT NULL,
    storage_uri VARCHAR NOT NULL,
    storage_type VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    record_count NUMBER NOT NULL,
    checksum VARCHAR NOT NULL,

    creator VARCHAR NOT NULL,
    created_at TIMESTAMP_TZ NOT NULL,
    status VARCHAR NOT NULL,
    provenance VARCHAR NOT NULL DEFAULT 'MANAGED',
    source_system VARCHAR,
    source_reference VARCHAR,

    UNIQUE (
        name,
        version
    )
);

CREATE TABLE IF NOT EXISTS experiment (

    experiment_id VARCHAR NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,
    description VARCHAR NOT NULL,
    owner VARCHAR NOT NULL,
    created_at TIMESTAMP_TZ NOT NULL,
    updated_at TIMESTAMP_TZ,
    status VARCHAR NOT NULL,

    UNIQUE (
        name
    )
);

ALTER TABLE experiment ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP_TZ;

CREATE TABLE IF NOT EXISTS experiment_candidate (

    candidate_id VARCHAR NOT NULL PRIMARY KEY,
    experiment_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,

    prompt_id VARCHAR NOT NULL,
    prompt_version VARCHAR NOT NULL,
    model_id VARCHAR NOT NULL,
    model_version VARCHAR NOT NULL,
    dataset_id VARCHAR NOT NULL,
    dataset_version VARCHAR NOT NULL,

    evaluation_provider VARCHAR NOT NULL,
    temperature FLOAT NOT NULL,
    top_p FLOAT NOT NULL,
    max_tokens NUMBER NOT NULL,
    metadata_json VARIANT NOT NULL,
    created_at TIMESTAMP_TZ NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_run (

    run_id VARCHAR NOT NULL PRIMARY KEY,
    experiment_id VARCHAR NOT NULL,
    candidate_id VARCHAR NOT NULL,
    dataset_version VARCHAR NOT NULL,
    evaluation_provider VARCHAR NOT NULL,
    evaluation_result_id VARCHAR,
    started_at TIMESTAMP_TZ,
    completed_at TIMESTAMP_TZ,
    status VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS leaderboard (

    leaderboard_id VARCHAR NOT NULL PRIMARY KEY,
    experiment_id VARCHAR NOT NULL,
    ranking_strategy VARCHAR NOT NULL,
    generated_at TIMESTAMP_TZ NOT NULL
);

CREATE TABLE IF NOT EXISTS leaderboard_entry (

    leaderboard_id VARCHAR NOT NULL,
    rank NUMBER NOT NULL,
    candidate_id VARCHAR NOT NULL,
    overall_score FLOAT NOT NULL,
    metrics_json VARIANT NOT NULL,
    cost FLOAT,
    latency FLOAT,
    reason VARCHAR NOT NULL,

    PRIMARY KEY (
        leaderboard_id,
        rank
    )
);

CREATE TABLE IF NOT EXISTS job_execution (

    job_id VARCHAR NOT NULL PRIMARY KEY,
    job_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    input_refs_json VARIANT NOT NULL,
    input_hash VARCHAR NOT NULL,
    idempotency_key VARCHAR NOT NULL,
    submitted_by VARCHAR NOT NULL,
    attempt_count NUMBER NOT NULL,
    max_attempts NUMBER NOT NULL,
    result_ref VARCHAR,
    failure_reason VARCHAR,
    leased_by VARCHAR,
    lease_expires_at TIMESTAMP_TZ,
    heartbeat_at TIMESTAMP_TZ,
    created_at TIMESTAMP_TZ NOT NULL,
    updated_at TIMESTAMP_TZ NOT NULL,
    started_at TIMESTAMP_TZ,
    completed_at TIMESTAMP_TZ,

    UNIQUE (
        job_type,
        idempotency_key
    )
);

CREATE TABLE IF NOT EXISTS worker_heartbeat (
    worker_id VARCHAR PRIMARY KEY,
    worker_type VARCHAR NOT NULL,
    heartbeat_at TIMESTAMP_TZ NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'RUNNING'
);

CREATE TABLE IF NOT EXISTS mcp_execution_audit (

    audit_id VARCHAR NOT NULL PRIMARY KEY,
    request_id VARCHAR NOT NULL,
    correlation_id VARCHAR NOT NULL,
    tool_name VARCHAR NOT NULL,
    tool_version VARCHAR NOT NULL,
    actor_id VARCHAR NOT NULL,
    actor_type VARCHAR NOT NULL,
    agent_name VARCHAR,
    agent_session_id VARCHAR,
    client_name VARCHAR,
    client_version VARCHAR,
    idempotency_key VARCHAR NOT NULL,
    operation_type VARCHAR NOT NULL,
    resource_type VARCHAR NOT NULL,
    resource_id VARCHAR,
    request_hash VARCHAR NOT NULL,
    request_summary_json VARIANT NOT NULL,
    resolved_versions_json VARIANT NOT NULL,
    reason VARCHAR NOT NULL,
    dry_run BOOLEAN NOT NULL,
    status VARCHAR NOT NULL,
    job_id VARCHAR,
    result_reference VARCHAR,
    error_code VARCHAR,
    error_message VARCHAR,
    started_at TIMESTAMP_TZ NOT NULL,
    completed_at TIMESTAMP_TZ,
    duration_ms FLOAT,
    metadata_json VARIANT NOT NULL
);

ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS provenance VARCHAR NOT NULL DEFAULT 'MANAGED';
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS source_system VARCHAR;
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS source_reference VARCHAR;
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS content_hash VARCHAR;
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS content_available BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE prompt_registry ALTER COLUMN template DROP NOT NULL;
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS provenance VARCHAR NOT NULL DEFAULT 'MANAGED';
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS source_system VARCHAR;
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS source_reference VARCHAR;
ALTER TABLE dataset_registry ADD COLUMN IF NOT EXISTS provenance VARCHAR NOT NULL DEFAULT 'MANAGED';
ALTER TABLE dataset_registry ADD COLUMN IF NOT EXISTS source_system VARCHAR;
ALTER TABLE dataset_registry ADD COLUMN IF NOT EXISTS source_reference VARCHAR;
