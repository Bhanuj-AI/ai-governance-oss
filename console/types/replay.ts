export type ReplayStatus =
  | "DRAFT"
  | "READY"
  | "QUEUED"
  | "RUNNING"
  | "EXECUTION_COMPLETED"
  | "EVALUATING"
  | "COMPARING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "ARCHIVED";

export type ReplayConfiguration = {
  workflow_id: string;
  workflow_version: string;
  execution_adapter: string;
  input_snapshot_ref: string;
  state_snapshot_ref: string;
  artifact_refs: string[];
  prompt_refs: string[];
  model_refs: string[];
  dataset_refs: string[];
  policy_refs: string[];
  runtime_parameters: Record<string, unknown>;
  configuration_source: string;
  resolved_at: string | null;
  configuration_hash: string;
};

export type ReplayFailure = {
  code: string;
  message: string;
  stage: string;
  details: Record<string, unknown>;
  occurred_at: string;
};

export type Replay = {
  replay_id: string;
  source_execution_id: string;
  status: ReplayStatus;
  mode: string;
  configuration: ReplayConfiguration | null;
  requested_by: string;
  organization_id: string;
  project_id: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  failure: ReplayFailure | null;
  metadata: Record<string, unknown>;
  job_id: string | null;
  replay_execution_id: string | null;
  queued_at: string | null;
  started_at: string | null;
  execution_completed_at: string | null;
  cancel_requested_at: string | null;
  cancelled_at: string | null;
  attempt_count: number;
  evaluation_job_id: string | null;
  baseline_evaluation_id: string | null;
  replay_evaluation_id: string | null;
  comparison_id: string | null;
  drift_id: string | null;
  result_id: string | null;
  evaluation_started_at: string | null;
  evaluation_completed_at: string | null;
  comparison_started_at: string | null;
  comparison_completed_at: string | null;
  completed_at: string | null;
};

export type ReplayResult = {
  result_id: string;
  replay_id: string;
  source_execution_id: string;
  replay_execution_id: string;
  baseline_evaluation_id: string;
  replay_evaluation_id: string;
  comparison_id: string;
  drift_id: string;
  baseline_strategy: string;
  comparison_summary: {
    metric_count: number;
    improved_metric_count: number;
    regressed_metric_count: number;
    unchanged_metric_count: number;
    new_metric_count: number;
    removed_metric_count: number;
    overall_score_delta: number | null;
  };
  drift_summary: {
    severity: string;
    changed_metrics: string[];
    new_metrics: string[];
    removed_metrics: string[];
    analyzer_version: string;
    threshold_policy: Record<string, unknown>;
  };
  created_at: string;
  metadata: Record<string, unknown>;
};

export type ReplayAuditRecord = {
  event_id: string;
  operation_type: string;
  status: string;
  occurred_at: string;
  resource_type: string;
  resource_id: string;
  detail: string;
  job_id: string | null;
  result_reference: string | null;
};

export type ReplayCreateRequest = {
  source_execution_id: string;
  idempotency_key: string;
  mode: "FULL";
  configuration_source: "ORIGINAL";
  metadata: Record<string, unknown>;
  reason?: string;
  dry_run?: boolean;
};

export type ReplayEvaluationRequest = {
  reason: string;
  baseline_strategy: "EXPLICIT" | "LATEST_COMPATIBLE" | "SOURCE_PRIMARY";
  baseline_evaluation_id?: string | null;
  evaluation_provider?: string | null;
  provider_installation_id?: string | null;
  dry_run?: boolean;
};

export type ReplayExecutionSearchItem = {
  execution_id: string;
  workflow_id: string;
  workflow_name: string;
  workflow_version: string;
  execution_status: string;
  created_at: string | null;
  replayable: boolean;
  replayability_reason: string | null;
};

export type ReplayExecutionSearchPage = {
  items: ReplayExecutionSearchItem[];
  next_cursor: string | null;
};
