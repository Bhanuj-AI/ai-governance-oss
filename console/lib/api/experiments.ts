import { kavachJsonRequest, kavachRequest } from "@/lib/api/client";

export type Experiment = { experiment_id: string; name: string; description: string; owner: string; status: string; created_at: string; updated_at?: string; metadata: Record<string, unknown> };
export type Candidate = { candidate_id: string; experiment_id: string; candidate_name: string; prompt_id: string; prompt_version: string; model_id: string; model_version: string; dataset_id: string; dataset_version: string; provider_name: string; provider_installation_id?: string | null; runtime_parameters: Record<string, unknown>; metadata: Record<string, unknown>; created_at: string };
export type MetricComparison = { metric_name: string; baseline_value?: number | null; candidate_value?: number | null; score_difference?: number | null };
export type CandidateComparison = { experiment_id: string; baseline_candidate: Candidate; comparison_candidate: Candidate; metric_comparisons: MetricComparison[] };
export type Run = { run_id: string; experiment_id: string; candidate_id: string; dataset_version: string; provider_name: string; evaluation_result_id?: string | null; started_at?: string | null; completed_at?: string | null; status: string };
export type Leaderboard = { leaderboard_id: string; experiment_id: string; ranking_strategy: string; generated_at: string; entries: { rank: number; candidate_id: string; overall_score: number; metrics: Record<string, number>; cost?: number | null; latency?: number | null; reason: string }[] };
export type RunResponse = { experiment_id: string; runs: Run[]; leaderboard?: Leaderboard | null };
export const listExperiments = () => kavachRequest<Experiment[]>("/api/v1/experiments");
export const getExperiment = (id: string) => kavachRequest<Experiment>(`/api/v1/experiments/${id}`);
export const listCandidates = (id: string) => kavachRequest<Candidate[]>(`/api/v1/experiments/${id}/candidates`);
export const listRuns = (id: string) => kavachRequest<Run[]>(`/api/v1/experiments/${id}/runs`);
export const createExperiment = (body: { name: string; description: string }) => kavachJsonRequest<Experiment, typeof body>("/api/v1/experiments", { method: "POST", body });
export const addCandidate = (id: string, body: Record<string, unknown>) => kavachJsonRequest<Candidate, Record<string, unknown>>(`/api/v1/experiments/${id}/candidates`, { method: "POST", body });
export const runExperiment = (id: string) => kavachJsonRequest<RunResponse, Record<string, unknown>>(`/api/v1/experiments/${id}/run`, { method: "POST", body: {} });
export const getLeaderboard = (id: string) => kavachRequest<Leaderboard>(`/api/v1/experiments/${id}/leaderboard`);
export const getCandidateComparison = (id: string, baselineCandidateId: string, comparisonCandidateId: string) => kavachRequest<CandidateComparison>(`/api/v1/experiments/${id}/comparison?baseline_candidate_id=${encodeURIComponent(baselineCandidateId)}&comparison_candidate_id=${encodeURIComponent(comparisonCandidateId)}`);
