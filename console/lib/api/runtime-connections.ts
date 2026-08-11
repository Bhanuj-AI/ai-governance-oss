import { aiGovernanceJsonRequest, aiGovernanceRequest } from "@/lib/api/client";

export type RuntimeConnection = {
  runtime_connection_id: string;
  display_name: string;
  provider: string;
  settings: Record<string, unknown>;
  secret_refs: Record<string, string>;
  enabled: boolean;
  status: "ACTIVE" | "DISABLED";
  organization_id: string;
  project_id: string | null;
  scope: "ORGANIZATION" | "PROJECT";
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  last_tested_at: string | null;
  last_test_status: "NOT_TESTED" | "SUCCEEDED" | "FAILED";
  last_test_message: string | null;
  version: number;
};

export type RuntimeConnectionInput = {
  display_name: string;
  provider: string;
  settings: Record<string, unknown>;
  secret_refs: Record<string, string>;
  enabled: boolean;
  scope: "ORGANIZATION" | "PROJECT";
};

export type RuntimeConnectionProvider = {
  key: string;
  display_name: string;
  allowed: boolean;
};

export const listRuntimeConnections = () => aiGovernanceRequest<RuntimeConnection[]>("/api/v1/runtime-connections");
export const listRuntimeConnectionProviders = () => aiGovernanceRequest<RuntimeConnectionProvider[]>("/api/v1/runtime-connections/providers");
export const validateRuntimeConnection = (payload: RuntimeConnectionInput) => aiGovernanceJsonRequest<{ valid: boolean; provider: string; message: string }, RuntimeConnectionInput>("/api/v1/runtime-connections/validate", { method: "POST", body: payload });
export const createRuntimeConnection = (payload: RuntimeConnectionInput) => aiGovernanceJsonRequest<RuntimeConnection, RuntimeConnectionInput>("/api/v1/runtime-connections", { method: "POST", body: payload });
export const updateRuntimeConnection = (connectionId: string, payload: Partial<Pick<RuntimeConnectionInput, "display_name" | "settings" | "secret_refs" | "enabled">>) => aiGovernanceJsonRequest<RuntimeConnection, typeof payload>(`/api/v1/runtime-connections/${encodeURIComponent(connectionId)}`, { method: "PATCH", body: payload });
export const testRuntimeConnection = (connectionId: string) => aiGovernanceJsonRequest<RuntimeConnection, undefined>(`/api/v1/runtime-connections/${encodeURIComponent(connectionId)}/test`, { method: "POST" });
