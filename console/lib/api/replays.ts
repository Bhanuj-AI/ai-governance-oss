import { kavachJsonRequest, kavachRequest, type QueryParams } from "@/lib/api/client";
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
  kavachRequest<Replay[]>("/api/v1/replays", params);

export const getReplay = (replayId: string) =>
  kavachRequest<Replay>(`/api/v1/replays/${encodeURIComponent(replayId)}`);

export const createReplay = (body: ReplayCreateRequest) =>
  kavachJsonRequest<Replay, ReplayCreateRequest>("/api/v1/replays", {
    method: "POST",
    body,
  });

export const validateReplay = (body: ReplayCreateRequest) =>
  kavachJsonRequest<Record<string, unknown>, ReplayCreateRequest>("/api/v1/replays", {
    method: "POST",
    body: { ...body, dry_run: true },
  });

export const submitReplay = (replayId: string, reason: string, dryRun = false) =>
  kavachJsonRequest<Replay | { replay: Replay }, { reason: string; dry_run: boolean }>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/submit`,
    { method: "POST", body: { reason, dry_run: dryRun } },
  );

export const cancelReplay = (replayId: string, reason: string) =>
  kavachJsonRequest<Replay, { reason: string; dry_run: boolean }>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/cancel`,
    { method: "POST", body: { reason, dry_run: false } },
  );

export const archiveReplay = (replayId: string, reason: string) =>
  kavachJsonRequest<Replay, { reason: string }>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/archive`,
    { method: "POST", body: { reason } },
  );

export const evaluateReplay = (
  replayId: string,
  body: ReplayEvaluationRequest,
) =>
  kavachJsonRequest<Replay, ReplayEvaluationRequest>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/evaluate`,
    { method: "POST", body },
  );

export const getReplayResult = (replayId: string) =>
  kavachRequest<ReplayResult>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/result`,
  );

export const getReplayAudit = (replayId: string) =>
  kavachRequest<ReplayAuditRecord[]>(
    `/api/v1/replays/${encodeURIComponent(replayId)}/audit`,
  );

export const searchReplayExecutions = (params?: QueryParams) =>
  kavachRequest<ReplayExecutionSearchPage>("/api/v1/replay-executions/search", params);

export const getReplayExecution = (executionId: string) =>
  kavachRequest<ReplayExecutionSearchItem>(
    `/api/v1/replay-executions/${encodeURIComponent(executionId)}`,
  );
