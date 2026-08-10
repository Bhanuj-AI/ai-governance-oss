import { aiGovernanceJsonRequest, aiGovernanceRequest, type QueryParams } from "@/lib/api/client";
import type {
  Replay,
  ReplayAuditRecord,
  ReplayCreateRequest,
  ReplayEvaluationRequest,
  ReplayExecutionSearchItem,
  ReplayExecutionSearchPage,
  ReplayResult,
} from "@/types/replay";

export const listReplays = (params?: QueryParams) =>
  aiGovernanceRequest<Replay[]>("/api/v1/replays", params);

export const getReplay = (replayId: string) =>
  aiGovernanceRequest<Replay>(`/api/v1/replays/${encodeURIComponent(replayId)}`);

export const createReplay = (body: ReplayCreateRequest) =>
  aiGovernanceJsonRequest<Replay, ReplayCreateRequest>("/api/v1/replays", {
    method: "POST",
    body,
  });

export const validateReplay = (body: ReplayCreateRequest) =>
  aiGovernanceJsonRequest<Record<string, unknown>, ReplayCreateRequest>("/api/v1/replays", {
    method: "POST",
    body: { ...body, dry_run: true },
  });

export const submitReplay = (replayId: string, reason: string, dryRun = false) =>
  aiGovernanceJsonRequest<Replay | { replay: Replay }, { reason: string; dry_run: boolean }>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/submit`,
    { method: "POST", body: { reason, dry_run: dryRun } },
  );

export const cancelReplay = (replayId: string, reason: string) =>
  aiGovernanceJsonRequest<Replay, { reason: string; dry_run: boolean }>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/cancel`,
    { method: "POST", body: { reason, dry_run: false } },
  );

export const archiveReplay = (replayId: string, reason: string) =>
  aiGovernanceJsonRequest<Replay, { reason: string }>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/archive`,
    { method: "POST", body: { reason } },
  );

export const evaluateReplay = (
  replayId: string,
  body: ReplayEvaluationRequest,
) =>
  aiGovernanceJsonRequest<Replay, ReplayEvaluationRequest>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/evaluate`,
    { method: "POST", body },
  );

export const getReplayResult = (replayId: string) =>
  aiGovernanceRequest<ReplayResult>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/result`,
  );

export const getReplayAudit = (replayId: string) =>
  aiGovernanceRequest<ReplayAuditRecord[]>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/audit`,
  );

export const searchReplayExecutions = (params?: QueryParams) =>
  aiGovernanceRequest<ReplayExecutionSearchPage>("/api/v1/replay-executions/search", params);

export const getReplayExecution = (executionId: string) =>
  aiGovernanceRequest<ReplayExecutionSearchItem>(
    `/api/v1/replay-executions/${encodeURIComponent(executionId)}`,
  );
