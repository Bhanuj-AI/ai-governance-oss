CREATE TABLE IF NOT EXISTS replay_execution_catalog (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    workflow_name TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    actor_id TEXT,
    actor_type TEXT,
    replayable BOOLEAN NOT NULL,
    replayability_code TEXT,
    replayability_summary TEXT,
    evaluation_available BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    projection_version INTEGER NOT NULL,
    PRIMARY KEY (organization_id, project_id, execution_id)
);
CREATE INDEX IF NOT EXISTS idx_replay_execution_catalog_tenant_order ON replay_execution_catalog(organization_id, project_id, executed_at DESC, execution_id DESC);
CREATE INDEX IF NOT EXISTS idx_replay_execution_catalog_workflow ON replay_execution_catalog(organization_id, project_id, workflow_id, executed_at DESC, execution_id DESC);
CREATE INDEX IF NOT EXISTS idx_replay_execution_catalog_status ON replay_execution_catalog(organization_id, project_id, execution_status, executed_at DESC, execution_id DESC);
CREATE INDEX IF NOT EXISTS idx_replay_execution_catalog_replayable ON replay_execution_catalog(organization_id, project_id, replayable, executed_at DESC, execution_id DESC);

CREATE TABLE IF NOT EXISTS replay_workflow_execution (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (organization_id, project_id, execution_id)
);

CREATE TABLE IF NOT EXISTS organizations (
    organization_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT NOT NULL,
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (organization_id, project_id),
    UNIQUE (organization_id, slug)
);

CREATE TABLE IF NOT EXISTS organization_memberships (
    organization_id TEXT NOT NULL REFERENCES organizations(organization_id),
    actor_id TEXT NOT NULL,
    display_name TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (organization_id, actor_id)
);

CREATE TABLE IF NOT EXISTS role_assignments (
    assignment_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT,
    actor_id TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL,
    FOREIGN KEY (organization_id, actor_id)
        REFERENCES organization_memberships(organization_id, actor_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES projects(organization_id, project_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_role_assignment_org
ON role_assignments(organization_id, actor_id, role)
WHERE project_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_role_assignment_project
ON role_assignments(organization_id, project_id, actor_id, role)
WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_org_status ON projects(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_membership_actor_status
ON organization_memberships(organization_id, actor_id, status);
CREATE INDEX IF NOT EXISTS idx_role_assignment_actor
ON role_assignments(organization_id, actor_id);
CREATE INDEX IF NOT EXISTS idx_role_assignment_project_actor
ON role_assignments(organization_id, project_id, actor_id);

CREATE TABLE IF NOT EXISTS authorization_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT,
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    permission TEXT NOT NULL,
    authorization_result BOOLEAN NOT NULL,
    reason_code TEXT NOT NULL,
    matched_roles_json JSONB NOT NULL,
    permission_model_version TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    request_id TEXT NOT NULL,
    correlation_id TEXT,
    occurred_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_authorization_audit_tenant_time
ON authorization_audit(organization_id, project_id, occurred_at);

CREATE TABLE IF NOT EXISTS agent_evaluation (

    evaluation_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,

    evaluator_type TEXT NOT NULL,
    evaluator_version TEXT NOT NULL,

    metric_name TEXT NOT NULL,
    metric_score DOUBLE PRECISION NOT NULL,

    metadata_json JSONB,
    provider_metadata_json JSONB,
    provider_descriptor_snapshot_json JSONB,
    artifacts_json JSONB,
    created_at TIMESTAMPTZ,
    explanation TEXT,

    PRIMARY KEY (
        evaluation_id,
        metric_name
    )
);

CREATE INDEX IF NOT EXISTS idx_agent_evaluation_execution
ON agent_evaluation(execution_id);

CREATE INDEX IF NOT EXISTS idx_agent_evaluation_metric
ON agent_evaluation(metric_name);

CREATE INDEX IF NOT EXISTS idx_agent_evaluation_evaluator
ON agent_evaluation(evaluator_type);

CREATE TABLE IF NOT EXISTS prompt_registry (

    prompt_id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,

    template TEXT,
    variables_json JSONB NOT NULL,

    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT 'MANAGED',
    source_system TEXT,
    source_reference TEXT,
    content_hash TEXT,
    content_available BOOLEAN NOT NULL DEFAULT TRUE,
    tenant_id TEXT NOT NULL DEFAULT 'org_default',
    organization_id TEXT NOT NULL DEFAULT 'org_default',
    project_id TEXT NOT NULL DEFAULT 'project_default',

    UNIQUE (
        name,
        version
    )
);

CREATE INDEX IF NOT EXISTS idx_prompt_registry_name
ON prompt_registry(name);

CREATE INDEX IF NOT EXISTS idx_prompt_registry_status
ON prompt_registry(status);

ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
UPDATE prompt_registry SET tenant_id=organization_id WHERE tenant_id='org_default';
CREATE INDEX IF NOT EXISTS idx_prompt_registry_tenant
ON prompt_registry(tenant_id, organization_id, project_id);

CREATE TABLE IF NOT EXISTS model_registry (

    model_id TEXT NOT NULL PRIMARY KEY,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,

    parameters_json JSONB NOT NULL,
    cost_json JSONB,
    latency DOUBLE PRECISION,
    context_window INTEGER NOT NULL,

    creator TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT 'MANAGED',
    source_system TEXT,
    source_reference TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'org_default',
    organization_id TEXT NOT NULL DEFAULT 'org_default',
    project_id TEXT NOT NULL DEFAULT 'project_default',

    UNIQUE (
        provider,
        model_name,
        version
    )
);

CREATE INDEX IF NOT EXISTS idx_model_registry_logical_model
ON model_registry(provider, model_name);

CREATE INDEX IF NOT EXISTS idx_model_registry_status
ON model_registry(status);

ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
UPDATE model_registry SET tenant_id=organization_id WHERE tenant_id='org_default';
CREATE INDEX IF NOT EXISTS idx_model_registry_tenant
ON model_registry(tenant_id, organization_id, project_id);

CREATE TABLE IF NOT EXISTS dataset_registry (

    dataset_id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,

    description TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    storage_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    checksum TEXT NOT NULL,

    creator TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    provenance TEXT NOT NULL DEFAULT 'MANAGED',
    source_system TEXT,
    source_reference TEXT,

    UNIQUE (
        name,
        version
    )
);

CREATE INDEX IF NOT EXISTS idx_dataset_registry_name
ON dataset_registry(name);

CREATE INDEX IF NOT EXISTS idx_dataset_registry_status
ON dataset_registry(status);

CREATE TABLE IF NOT EXISTS experiment (

    experiment_id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    owner TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ,
    status TEXT NOT NULL,

    UNIQUE (
        name
    )
);

CREATE INDEX IF NOT EXISTS idx_experiment_status
ON experiment(status);

ALTER TABLE experiment ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS replay (
    replay_id TEXT PRIMARY KEY,
    source_execution_id TEXT NOT NULL,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    configuration_json JSONB,
    requested_by TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    correlation_id TEXT,
    idempotency_key TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    archived_at TIMESTAMPTZ,
    failure_json JSONB,
    metadata_json JSONB NOT NULL,
    version INTEGER NOT NULL,
    job_id TEXT UNIQUE,
    replay_execution_id TEXT UNIQUE,
    queued_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    execution_completed_at TIMESTAMPTZ,
    cancel_requested_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    evaluation_job_id TEXT UNIQUE,
    baseline_evaluation_id TEXT,
    replay_evaluation_id TEXT,
    comparison_id TEXT,
    drift_id TEXT,
    result_id TEXT UNIQUE,
    evaluation_started_at TIMESTAMPTZ,
    evaluation_completed_at TIMESTAMPTZ,
    comparison_started_at TIMESTAMPTZ,
    comparison_completed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (organization_id, project_id, idempotency_key)
);

ALTER TABLE replay ADD COLUMN IF NOT EXISTS evaluation_job_id TEXT;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS baseline_evaluation_id TEXT;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS replay_evaluation_id TEXT;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS comparison_id TEXT;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS drift_id TEXT;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS result_id TEXT;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS evaluation_started_at TIMESTAMPTZ;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS evaluation_completed_at TIMESTAMPTZ;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS comparison_started_at TIMESTAMPTZ;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS comparison_completed_at TIMESTAMPTZ;
ALTER TABLE replay ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_replay_tenant_created
ON replay(organization_id, project_id, created_at DESC, replay_id DESC);
CREATE INDEX IF NOT EXISTS idx_replay_source_execution
ON replay(source_execution_id);
CREATE INDEX IF NOT EXISTS idx_replay_status ON replay(status);
CREATE INDEX IF NOT EXISTS idx_replay_requested_by ON replay(requested_by);
CREATE INDEX IF NOT EXISTS idx_replay_job_id ON replay(job_id);
CREATE INDEX IF NOT EXISTS idx_replay_execution_id ON replay(replay_execution_id);
CREATE INDEX IF NOT EXISTS idx_replay_evaluation_job_id ON replay(evaluation_job_id);
CREATE INDEX IF NOT EXISTS idx_replay_baseline_evaluation_id ON replay(baseline_evaluation_id);
CREATE INDEX IF NOT EXISTS idx_replay_replay_evaluation_id ON replay(replay_evaluation_id);
CREATE INDEX IF NOT EXISTS idx_replay_comparison_id ON replay(comparison_id);
CREATE INDEX IF NOT EXISTS idx_replay_drift_id ON replay(drift_id);
CREATE INDEX IF NOT EXISTS idx_replay_result_id ON replay(result_id);
CREATE INDEX IF NOT EXISTS idx_replay_completed_at ON replay(completed_at);

CREATE TABLE IF NOT EXISTS replay_result (
    result_id TEXT PRIMARY KEY,
    replay_id TEXT NOT NULL UNIQUE,
    source_execution_id TEXT NOT NULL,
    replay_execution_id TEXT NOT NULL,
    baseline_evaluation_id TEXT NOT NULL,
    replay_evaluation_id TEXT NOT NULL,
    comparison_id TEXT NOT NULL,
    drift_id TEXT NOT NULL,
    baseline_strategy TEXT NOT NULL,
    comparison_summary_json JSONB NOT NULL,
    drift_summary_json JSONB NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    metadata_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_replay_result_tenant_created ON replay_result(organization_id, project_id, created_at DESC, result_id DESC);
CREATE INDEX IF NOT EXISTS idx_replay_result_source_execution ON replay_result(source_execution_id);
CREATE INDEX IF NOT EXISTS idx_replay_result_replay_execution ON replay_result(replay_execution_id);

CREATE TABLE IF NOT EXISTS experiment_candidate (

    candidate_id TEXT NOT NULL PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    name TEXT NOT NULL,

    prompt_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_version TEXT NOT NULL,

    evaluation_provider TEXT NOT NULL,
    temperature DOUBLE PRECISION NOT NULL,
    top_p DOUBLE PRECISION NOT NULL,
    max_tokens INTEGER NOT NULL,
    metadata_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_experiment_candidate_experiment_id
ON experiment_candidate(experiment_id);

CREATE TABLE IF NOT EXISTS evaluation_run (

    run_id TEXT NOT NULL PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    evaluation_provider TEXT NOT NULL,
    evaluation_result_id TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    failure_reason TEXT,
    total_item_count INTEGER,
    completed_item_count INTEGER NOT NULL DEFAULT 0,
    evaluated_item_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_evaluation_run_experiment_id
ON evaluation_run(experiment_id);

CREATE INDEX IF NOT EXISTS idx_evaluation_run_candidate_id
ON evaluation_run(candidate_id);

CREATE TABLE IF NOT EXISTS leaderboard (

    leaderboard_id TEXT NOT NULL PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    ranking_strategy TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leaderboard_experiment_id
ON leaderboard(experiment_id);

CREATE INDEX IF NOT EXISTS idx_leaderboard_strategy
ON leaderboard(ranking_strategy);

CREATE TABLE IF NOT EXISTS leaderboard_entry (

    leaderboard_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    candidate_id TEXT NOT NULL,
    overall_score DOUBLE PRECISION NOT NULL,
    metrics_json JSONB NOT NULL,
    cost DOUBLE PRECISION,
    latency DOUBLE PRECISION,
    reason TEXT NOT NULL,

    PRIMARY KEY (
        leaderboard_id,
        rank
    )
);

CREATE INDEX IF NOT EXISTS idx_leaderboard_entry_candidate_id
ON leaderboard_entry(candidate_id);

CREATE TABLE IF NOT EXISTS job_execution (

    job_id TEXT NOT NULL PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_refs_json JSONB NOT NULL,
    input_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    attempt_count INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    result_ref TEXT,
    failure_reason TEXT,
    leased_by TEXT,
    lease_expires_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    organization_id TEXT NOT NULL DEFAULT 'org_default',
    project_id TEXT NOT NULL DEFAULT 'project_default',
    execution_context_json JSONB,

    UNIQUE (
        organization_id,
        project_id,
        job_type,
        idempotency_key
    )
);

CREATE INDEX IF NOT EXISTS idx_job_execution_status
ON job_execution(status);

CREATE INDEX IF NOT EXISTS idx_job_execution_type_status
ON job_execution(job_type, status);

CREATE TABLE IF NOT EXISTS worker_heartbeat (
    worker_id TEXT PRIMARY KEY,
    worker_type TEXT NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING'
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeat_at
ON worker_heartbeat(heartbeat_at);

CREATE TABLE IF NOT EXISTS ontology_sync_event (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    scope_identifier TEXT,
    correlation_id TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    status TEXT NOT NULL,
    retry_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    next_retry_at TIMESTAMPTZ,
    last_error TEXT,
    failed_at TIMESTAMPTZ,
    reconciliation_report_json JSONB,
    locked_by TEXT,
    lock_expires_at TIMESTAMPTZ,
    organization_id TEXT NOT NULL DEFAULT 'org_default',
    project_id TEXT NOT NULL DEFAULT 'project_default'
);
CREATE INDEX IF NOT EXISTS idx_ontology_sync_event_status
ON ontology_sync_event(status);
CREATE INDEX IF NOT EXISTS idx_ontology_sync_event_entity
ON ontology_sync_event(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_ontology_sync_event_correlation
ON ontology_sync_event(correlation_id);
CREATE INDEX IF NOT EXISTS idx_ontology_sync_event_due
ON ontology_sync_event(status, next_retry_at, lock_expires_at);

CREATE TABLE IF NOT EXISTS mcp_execution_audit (

    audit_id TEXT NOT NULL PRIMARY KEY,
    request_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    agent_name TEXT,
    agent_session_id TEXT,
    client_name TEXT,
    client_version TEXT,
    idempotency_key TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    request_hash TEXT NOT NULL,
    request_summary_json JSONB NOT NULL,
    resolved_versions_json JSONB NOT NULL,
    reason TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL,
    status TEXT NOT NULL,
    job_id TEXT,
    result_reference TEXT,
    error_code TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms DOUBLE PRECISION,
    metadata_json JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mcp_execution_audit_request_id
ON mcp_execution_audit(request_id);

CREATE INDEX IF NOT EXISTS idx_mcp_execution_audit_idempotency
ON mcp_execution_audit(idempotency_key);

CREATE INDEX IF NOT EXISTS idx_mcp_execution_audit_tool_status
ON mcp_execution_audit(tool_name, status);

-- Invocation evidence is separate from mutation evidence.  A read-only MCP
-- call belongs here; a governed write may have one row here and a distinct
-- row in mcp_execution_audit.
CREATE TABLE IF NOT EXISTS mcp_invocation_audit (
    invocation_id TEXT NOT NULL PRIMARY KEY,
    request_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT,
    actor_id TEXT,
    actor_type TEXT,
    client_id TEXT,
    status TEXT NOT NULL,
    authorization_decision TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    argument_summary_json JSONB NOT NULL,
    response_classification TEXT,
    response_hash TEXT,
    error_category TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_mcp_invocation_audit_scope_started
ON mcp_invocation_audit(organization_id, project_id, started_at);
CREATE INDEX IF NOT EXISTS idx_mcp_invocation_audit_tool_status
ON mcp_invocation_audit(tool_name, status);

CREATE TABLE IF NOT EXISTS governance_decision (

    decision_id TEXT NOT NULL PRIMARY KEY,
    decision_type TEXT NOT NULL,
    status TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence_json JSONB NOT NULL,
    policies_json JSONB NOT NULL,
    provenance_json JSONB NOT NULL,
    supersession_json JSONB NOT NULL,
    explanation_json JSONB,
    metadata_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    finalized_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_governance_decision_target
ON governance_decision(target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_governance_decision_status
ON governance_decision(status);

CREATE INDEX IF NOT EXISTS idx_governance_decision_correlation
ON governance_decision((provenance_json ->> 'correlation_id'));

CREATE INDEX IF NOT EXISTS idx_governance_decision_request
ON governance_decision((provenance_json ->> 'request_id'));

CREATE TABLE IF NOT EXISTS governance_decision_audit (

    audit_id TEXT NOT NULL PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES governance_decision(decision_id),
    action TEXT NOT NULL,
    actor_id TEXT,
    producer_id TEXT NOT NULL,
    correlation_id TEXT,
    request_id TEXT,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    metadata_json JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_governance_decision_audit_decision
ON governance_decision_audit(decision_id, created_at);

CREATE INDEX IF NOT EXISTS idx_governance_decision_audit_correlation
ON governance_decision_audit(correlation_id);

CREATE TABLE IF NOT EXISTS policy_definition (

    policy_id TEXT NOT NULL PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    owner TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    metadata_json JSONB NOT NULL,

    UNIQUE (
        project_id,
        name
    )
);

CREATE INDEX IF NOT EXISTS idx_policy_definition_organization
ON policy_definition(organization_id);

CREATE INDEX IF NOT EXISTS idx_policy_definition_project
ON policy_definition(project_id);

CREATE INDEX IF NOT EXISTS idx_policy_definition_category
ON policy_definition(category);

CREATE INDEX IF NOT EXISTS idx_policy_definition_owner
ON policy_definition(owner);

CREATE INDEX IF NOT EXISTS idx_policy_definition_created_at
ON policy_definition(created_at);

CREATE TABLE IF NOT EXISTS policy_version (

    policy_id TEXT NOT NULL REFERENCES policy_definition(policy_id),
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    target_types_json JSONB NOT NULL,
    rules_json JSONB NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    activated_at TIMESTAMPTZ,
    deprecated_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    metadata_json JSONB NOT NULL,

    PRIMARY KEY (
        policy_id,
        version
    )
);

CREATE INDEX IF NOT EXISTS idx_policy_version_policy
ON policy_version(policy_id);

CREATE INDEX IF NOT EXISTS idx_policy_version_status
ON policy_version(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_policy_version_one_active
ON policy_version(policy_id)
WHERE status = 'ACTIVE';

ALTER TABLE agent_evaluation ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE agent_evaluation ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE dataset_registry ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE dataset_registry ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS provenance TEXT NOT NULL DEFAULT 'MANAGED';
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS source_system TEXT;
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS source_reference TEXT;
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE prompt_registry ADD COLUMN IF NOT EXISTS content_available BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE prompt_registry ALTER COLUMN template DROP NOT NULL;
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS provenance TEXT NOT NULL DEFAULT 'MANAGED';
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS source_system TEXT;
ALTER TABLE model_registry ADD COLUMN IF NOT EXISTS source_reference TEXT;
ALTER TABLE dataset_registry ADD COLUMN IF NOT EXISTS provenance TEXT NOT NULL DEFAULT 'MANAGED';
ALTER TABLE dataset_registry ADD COLUMN IF NOT EXISTS source_system TEXT;
ALTER TABLE dataset_registry ADD COLUMN IF NOT EXISTS source_reference TEXT;
ALTER TABLE experiment ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE experiment ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE experiment_candidate ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE experiment_candidate ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE evaluation_run ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE evaluation_run ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE evaluation_run ADD COLUMN IF NOT EXISTS total_item_count INTEGER;
ALTER TABLE evaluation_run ADD COLUMN IF NOT EXISTS completed_item_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE evaluation_run ADD COLUMN IF NOT EXISTS evaluated_item_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leaderboard ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE leaderboard ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE mcp_execution_audit ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE mcp_execution_audit ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE governance_decision ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE governance_decision ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE governance_decision_audit ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE governance_decision_audit ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';
ALTER TABLE policy_version ADD COLUMN IF NOT EXISTS organization_id TEXT NOT NULL DEFAULT 'org_default';
ALTER TABLE policy_version ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT 'project_default';

CREATE INDEX IF NOT EXISTS idx_job_execution_tenant_status
ON job_execution(organization_id, project_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_governance_decision_tenant
ON governance_decision(organization_id, project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_mcp_audit_tenant
ON mcp_execution_audit(organization_id, project_id, started_at);

CREATE TABLE IF NOT EXISTS runtime_setting (
    key TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    value_json JSONB NOT NULL,
    version INTEGER NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (key, scope_type, scope_id)
);

ALTER TABLE runtime_setting ADD COLUMN IF NOT EXISTS scope_type TEXT NOT NULL DEFAULT 'SYSTEM';
ALTER TABLE runtime_setting ADD COLUMN IF NOT EXISTS scope_id TEXT NOT NULL DEFAULT '';
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'runtime_setting'::regclass
          AND contype = 'p'
          AND array_length(conkey, 1) = 1
    ) THEN
        ALTER TABLE runtime_setting DROP CONSTRAINT runtime_setting_pkey;
        ALTER TABLE runtime_setting ADD PRIMARY KEY (key, scope_type, scope_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS setting_audit (
    audit_id TEXT NOT NULL PRIMARY KEY,
    key TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    old_value_json JSONB,
    new_value_json JSONB NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE setting_audit ADD COLUMN IF NOT EXISTS scope_type TEXT NOT NULL DEFAULT 'SYSTEM';
ALTER TABLE setting_audit ADD COLUMN IF NOT EXISTS scope_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_setting_audit_key_created
ON setting_audit(key, scope_type, scope_id, created_at);

-- Agent Execution Trace
CREATE TABLE IF NOT EXISTS agent_execution (
    execution_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    external_execution_id TEXT NOT NULL,
    runtime_provider TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    correlation_id TEXT,
    parent_execution_id TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (organization_id, project_id, execution_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_execution_external
ON agent_execution(organization_id, project_id, external_execution_id, runtime_provider);

CREATE INDEX IF NOT EXISTS idx_agent_execution_tenant_order
ON agent_execution(organization_id, project_id, created_at DESC, execution_id DESC);

CREATE INDEX IF NOT EXISTS idx_agent_execution_agent
ON agent_execution(organization_id, project_id, agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_execution_status
ON agent_execution(organization_id, project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_execution_runtime
ON agent_execution(organization_id, project_id, runtime_provider, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_execution_event (
    event_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    late_for_runtime_findings BOOLEAN NOT NULL DEFAULT FALSE,
    runtime_findings_finalization_cutoff_at TIMESTAMPTZ,
    runtime_findings_lateness_policy_hours INTEGER,
    correlation_id TEXT,
    causation_id TEXT,
    actor_id TEXT,
    actor_type TEXT,
    resource_references_json JSONB NOT NULL DEFAULT '[]',
    evidence_references_json JSONB NOT NULL DEFAULT '[]',
    attributes_json JSONB NOT NULL DEFAULT '{}',
    event_schema_version TEXT NOT NULL DEFAULT '1',
    idempotency_key TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (organization_id, project_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_execution_event_execution_seq
ON agent_execution_event(organization_id, project_id, execution_id, sequence_number ASC);

CREATE INDEX IF NOT EXISTS idx_agent_execution_event_type
ON agent_execution_event(organization_id, project_id, execution_id, event_type, occurred_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_execution_event_idempotency
ON agent_execution_event(organization_id, project_id, execution_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_execution_event_actor
ON agent_execution_event(organization_id, project_id, execution_id, actor_id);

-- Runtime ontology projection state — durable outside Neo4j.
CREATE TABLE IF NOT EXISTS runtime_ontology_projection (
    execution_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    projection_version TEXT NOT NULL DEFAULT '1',
    source_version INTEGER NOT NULL DEFAULT 0,
    relationships_projected INTEGER NOT NULL DEFAULT 0,
    unresolved_json JSONB NOT NULL DEFAULT '[]',
    last_projected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1',
    PRIMARY KEY (organization_id, project_id, execution_id)
);

CREATE INDEX IF NOT EXISTS idx_runtime_projection_status
ON runtime_ontology_projection(organization_id, project_id, status);

CREATE INDEX IF NOT EXISTS idx_runtime_projection_updated
ON runtime_ontology_projection(organization_id, project_id, updated_at DESC);

-- Runtime findings — durable operational observations.
CREATE TABLE IF NOT EXISTS runtime_finding (
    finding_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    finding_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    status TEXT NOT NULL DEFAULT 'OPEN',
    lifecycle TEXT NOT NULL DEFAULT 'OPERATIONAL',
    baseline_window TEXT NOT NULL DEFAULT '7d',
    observation_window TEXT NOT NULL DEFAULT '24h',
    baseline_metrics_json JSONB NOT NULL DEFAULT '[]',
    observed_metrics_json JSONB NOT NULL DEFAULT '[]',
    observation_count INTEGER NOT NULL DEFAULT 0,
    consecutive_normal_windows INTEGER NOT NULL DEFAULT 0,
    healthy_reconciliation_windows_json JSONB NOT NULL DEFAULT '[]',
    last_reconciliation_json JSONB,
    reviews_json JSONB NOT NULL DEFAULT '[]',
    evidence_references_json JSONB NOT NULL DEFAULT '[]',
    related_execution_ids_json JSONB NOT NULL DEFAULT '[]',
    detector_id TEXT NOT NULL,
    detector_version TEXT NOT NULL DEFAULT '1',
    first_detected_at TIMESTAMPTZ,
    last_detected_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (organization_id, project_id, finding_id)
);

CREATE INDEX IF NOT EXISTS idx_runtime_finding_status
ON runtime_finding(organization_id, project_id, status);

CREATE INDEX IF NOT EXISTS idx_runtime_finding_type
ON runtime_finding(organization_id, project_id, finding_type);

CREATE INDEX IF NOT EXISTS idx_runtime_finding_subject
ON runtime_finding(organization_id, project_id, subject_type, subject_id);

CREATE INDEX IF NOT EXISTS idx_runtime_finding_created
ON runtime_finding(organization_id, project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS causal_audit (
    audit_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    execution_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    classification TEXT,
    evaluator_ref TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    version INTEGER NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (organization_id, project_id, audit_id),
    UNIQUE (organization_id, project_id, request_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_causal_audit_execution ON causal_audit(organization_id, project_id, execution_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_causal_audit_agent ON causal_audit(organization_id, project_id, agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_causal_audit_status ON causal_audit(organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_causal_audit_classification ON causal_audit(organization_id, project_id, classification, created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_intervention_policy (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    provider_version TEXT NOT NULL,
    policy_digest TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (organization_id, project_id, policy_id, version)
);
CREATE INDEX IF NOT EXISTS idx_evidence_intervention_policy_selector ON evidence_intervention_policy(organization_id, project_id, status, tool_name, schema_id, schema_version);

-- Hardening Check 3: Sustained recovery for auto-resolution
ALTER TABLE runtime_finding ADD COLUMN IF NOT EXISTS consecutive_normal_windows INTEGER NOT NULL DEFAULT 0;
ALTER TABLE runtime_finding ADD COLUMN IF NOT EXISTS healthy_reconciliation_windows_json JSONB NOT NULL DEFAULT '[]';
ALTER TABLE runtime_finding ADD COLUMN IF NOT EXISTS last_reconciliation_json JSONB;
ALTER TABLE runtime_finding ADD COLUMN IF NOT EXISTS lifecycle TEXT NOT NULL DEFAULT 'OPERATIONAL';
ALTER TABLE runtime_finding ADD COLUMN IF NOT EXISTS reviews_json JSONB NOT NULL DEFAULT '[]';
UPDATE runtime_finding SET lifecycle = 'CASE_REVIEW'
WHERE detector_id = 'causal_audit' AND lifecycle = 'OPERATIONAL';
ALTER TABLE agent_execution_event ADD COLUMN IF NOT EXISTS late_for_runtime_findings BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agent_execution_event ADD COLUMN IF NOT EXISTS runtime_findings_finalization_cutoff_at TIMESTAMPTZ;
ALTER TABLE agent_execution_event ADD COLUMN IF NOT EXISTS runtime_findings_lateness_policy_hours INTEGER;
