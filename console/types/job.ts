export type JobStatus =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED";

export type JobType =
  | "EVALUATION"
  | "EXPERIMENT"
  | "REPLAY"
  | "REPLAY_EXECUTION"
  | "REPLAY_EVALUATION"
  | "DRIFT_ANALYSIS";

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type JsonObject = Record<string, JsonValue>;

export type JobDto = {
  job_id: string;
  job_type: JobType;
  status: JobStatus;
  input_refs: JsonObject;
  input_hash: string;
  idempotency_key: string;
  submitted_by: string;
  attempt_count: number;
  max_attempts: number;
  result_ref: string | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type JobListDto = {
  jobs: JobDto[];
};

export type JobResultDto = {
  job_id: string;
  status: JobStatus;
  result_ref: string | null;
  failure_reason: string | null;
};

export type SubmitJobRequest = {
  job_type: JobType;
  input_refs: JsonObject;
  idempotency_key: string;
  submitted_by: string;
  max_attempts: number;
};

export type Job = {
  jobId: string;
  jobType: JobType;
  status: JobStatus;
  inputRefs: JsonObject;
  inputHash: string;
  idempotencyKey: string;
  submittedBy: string;
  attemptCount: number;
  maxAttempts: number;
  resultRef: string | null;
  failureReason: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt: string | null;
  completedAt: string | null;
};

export type JobResult = {
  jobId: string;
  status: JobStatus;
  resultRef: string | null;
  failureReason: string | null;
};
