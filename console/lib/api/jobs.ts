import {
  aiGovernanceJsonRequest,
  aiGovernanceRequest,
  type QueryParams,
} from "@/lib/api/client";
import type {
  Job,
  JobDto,
  JobListDto,
  JobResult,
  JobResultDto,
  SubmitJobRequest,
} from "@/types/job";

export async function getJobs(params?: QueryParams) {
  const dto = await aiGovernanceRequest<JobListDto>("/api/v1/jobs", params);
  return dto.jobs.map(mapJob);
}

export async function getJob(jobId: string) {
  const dto = await aiGovernanceRequest<JobDto>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}`,
  );
  return mapJob(dto);
}

export async function submitJob(request: SubmitJobRequest) {
  const dto = await aiGovernanceJsonRequest<JobDto, SubmitJobRequest>(
    "/api/v1/jobs",
    { method: "POST", body: request },
  );
  return mapJob(dto);
}

export async function cancelJob(jobId: string) {
  const dto = await aiGovernanceJsonRequest<JobDto, undefined>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
  );
  return mapJob(dto);
}

export async function retryJob(jobId: string) {
  const dto = await aiGovernanceJsonRequest<JobDto, undefined>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/retry`,
    { method: "POST" },
  );
  return mapJob(dto);
}

export async function getJobResult(jobId: string) {
  const dto = await aiGovernanceRequest<JobResultDto>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/result`,
  );
  return mapJobResult(dto);
}

function mapJob(dto: JobDto): Job {
  return {
    jobId: dto.job_id,
    jobType: dto.job_type,
    status: dto.status,
    inputRefs: dto.input_refs,
    inputHash: dto.input_hash,
    idempotencyKey: dto.idempotency_key,
    submittedBy: dto.submitted_by,
    attemptCount: dto.attempt_count,
    maxAttempts: dto.max_attempts,
    resultRef: dto.result_ref,
    failureReason: dto.failure_reason,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    startedAt: dto.started_at,
    completedAt: dto.completed_at,
  };
}

function mapJobResult(dto: JobResultDto): JobResult {
  return {
    jobId: dto.job_id,
    status: dto.status,
    resultRef: dto.result_ref,
    failureReason: dto.failure_reason,
  };
}
