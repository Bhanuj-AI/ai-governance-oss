import { aiGovernanceFormRequest, aiGovernanceJsonRequest, aiGovernanceRequest } from "@/lib/api/client";

export type PromptAsset = {
  prompt_id: string;
  name: string;
  version: string;
  variables: string[];
  created_at: string;
  created_by: string;
  status: string;
  provenance: "MANAGED" | "OBSERVED" | "IMPORTED";
  source_system: string | null;
  source_reference: string | null;
  content_hash: string | null;
  content_available: boolean;
};

export type PromptDetailAsset = PromptAsset & { template: string | null };
export type PromptCreateInput = Pick<PromptAsset, "name" | "version" | "variables"> & { template: string };

export type ModelAsset = {
  model_id: string;
  provider: string;
  model_name: string;
  provider_model_id: string | null;
  version: string;
  parameters: Record<string, unknown>;
  context_window: number;
  creator: string;
  created_at: string;
  status: string;
  provenance: "MANAGED" | "OBSERVED" | "IMPORTED";
  source_system: string | null;
  source_reference: string | null;
  runtime_capabilities: ModelRuntimeCapabilities;
};
export type RuntimeParameterCapability = { name: string; supported: boolean; value_type: "number" | "integer"; minimum: number | null; maximum: number | null; default: unknown | null };
export type ModelRuntimeCapabilities = { profile_id: string; profile_version: string; invocation_contract: string; verification: "DECLARED" | "VERIFIED" | "UNVERIFIED" | "OBSERVED"; parameters: RuntimeParameterCapability[] };
export type ModelRegisterInput = Pick<ModelAsset, "provider" | "model_name" | "provider_model_id" | "version" | "parameters" | "context_window"> & { cost?: Record<string, number> | null; latency?: number | null };
export type ModelVersionCreateInput = Pick<ModelRegisterInput, "version"> & Partial<Pick<ModelRegisterInput, "provider_model_id" | "parameters" | "cost" | "latency" | "context_window">>;
export type RuntimeModelProvider = { key: string; display_name: string; allowed: boolean };

export type DatasetAsset = {
  dataset_id: string;
  name: string;
  version: string;
  description: string;
  storage_uri: string;
  storage_type: string;
  schema_version: string;
  record_count: number;
  checksum: string;
  creator: string;
  created_at: string;
  status: string;
  provenance: "MANAGED" | "OBSERVED" | "IMPORTED";
  source_system: string | null;
  source_reference: string | null;
};

export type ProviderAsset = {
  name: string;
  display_name: string;
  version: string;
  adapter_version: string;
  config_schema_version: string;
  configuration_schema: ProviderConfigurationSchema;
  capabilities: {
    supported_metrics: string[];
    supported_evaluation_modes: string[];
    supports_batch: boolean;
    supports_async: boolean;
    supports_artifacts: boolean;
    supports_explanations: boolean;
    supports_row_level_results: boolean;
    metadata: Record<string, unknown>;
  };
  metadata: Record<string, unknown>;
};

export type ProviderConfigurationField = {
  type?: "string" | "integer" | "number" | "boolean" | "array";
  title?: string;
  description?: string;
  default?: unknown;
  items?: { enum?: string[] };
};

export type ProviderConfigurationSchema = {
  documentation_url?: string;
  settings?: { properties?: Record<string, ProviderConfigurationField>; required?: string[] };
  secret_refs?: { properties?: Record<string, ProviderConfigurationField>; required?: string[] };
};

export type ProviderInstallation = {
  installation_id: string;
  provider_type: string;
  adapter_version: string;
  display_name: string;
  settings: Record<string, unknown>;
  secret_refs: Record<string, string>;
  enabled: boolean;
  organization_id: string;
  project_id: string | null;
  scope: "ORGANIZATION" | "PROJECT";
  created_by: string;
  created_at: string;
  updated_at: string;
  version: number;
};

export type ProviderInstallationValidation = {
  valid: boolean;
  provider_type: string;
  message: string;
};

export const listPromptAssets = () => aiGovernanceRequest<PromptAsset[]>("/api/v1/prompts");
export const createPromptAsset = (payload: PromptCreateInput) => aiGovernanceJsonRequest<PromptAsset, PromptCreateInput>("/api/v1/prompts", { method: "POST", body: payload });
export const createPromptVersion = (promptId: string, payload: Pick<PromptCreateInput, "version"> & Partial<Pick<PromptCreateInput, "template" | "variables">>) => aiGovernanceJsonRequest<PromptAsset, typeof payload>(`/api/v1/prompts/${encodeURIComponent(promptId)}/versions`, { method: "POST", body: payload });
export const listPromptVersions = (name: string) =>
  aiGovernanceRequest<PromptAsset[]>(`/api/v1/prompts/${encodeURIComponent(name)}`);
export const getPromptVersion = (promptId: string) =>
  aiGovernanceRequest<PromptDetailAsset>(`/api/v1/prompts/versions/${encodeURIComponent(promptId)}`);
export const listModelAssets = () => aiGovernanceRequest<ModelAsset[]>("/api/v1/models");
export const listRuntimeModelProviders = () => aiGovernanceRequest<RuntimeModelProvider[]>("/api/v1/models/runtime-providers");
export const resolveModelRuntimeCapabilities = (payload: Pick<ModelAsset, "provider" | "model_name" | "provider_model_id">) => aiGovernanceJsonRequest<ModelRuntimeCapabilities, typeof payload>("/api/v1/models/runtime-capabilities/resolve", { method: "POST", body: payload });
export const registerModelAsset = (payload: ModelRegisterInput) => aiGovernanceJsonRequest<ModelAsset, ModelRegisterInput>("/api/v1/models", { method: "POST", body: payload });
export const createModelVersion = (modelId: string, payload: ModelVersionCreateInput) => aiGovernanceJsonRequest<ModelAsset, ModelVersionCreateInput>(`/api/v1/models/${encodeURIComponent(modelId)}/versions`, { method: "POST", body: payload });
export const activateModelAsset = (modelId: string) => aiGovernanceJsonRequest<ModelAsset, undefined>(`/api/v1/models/${encodeURIComponent(modelId)}/activate`, { method: "POST" });
export const deprecateModelAsset = (modelId: string) => aiGovernanceJsonRequest<ModelAsset, undefined>(`/api/v1/models/${encodeURIComponent(modelId)}/deprecate`, { method: "POST" });
export const archiveModelAsset = (modelId: string) => aiGovernanceJsonRequest<ModelAsset, undefined>(`/api/v1/models/${encodeURIComponent(modelId)}/archive`, { method: "POST" });
export const listDatasetAssets = () => aiGovernanceRequest<DatasetAsset[]>("/api/v1/datasets");
export const uploadDatasetAsset = (form: FormData) =>
  aiGovernanceFormRequest<DatasetAsset>("/api/v1/datasets/upload", form);
export const listProviderAssets = () => aiGovernanceRequest<ProviderAsset[]>("/api/v1/providers");
export const listProviderInstallations = () => aiGovernanceRequest<ProviderInstallation[]>("/api/v1/provider-installations");
export const createProviderInstallation = (payload: Pick<ProviderInstallation, "provider_type" | "display_name" | "settings" | "secret_refs" | "enabled" | "scope">) =>
  aiGovernanceJsonRequest<ProviderInstallation, typeof payload>("/api/v1/provider-installations", { method: "POST", body: payload });
export const validateProviderInstallation = (payload: Pick<ProviderInstallation, "provider_type" | "display_name" | "settings" | "secret_refs" | "enabled" | "scope">) =>
  aiGovernanceJsonRequest<ProviderInstallationValidation, typeof payload>("/api/v1/provider-installations/validate", { method: "POST", body: payload });
export const updateProviderInstallation = (installationId: string, payload: Partial<Pick<ProviderInstallation, "display_name" | "settings" | "secret_refs" | "enabled">>) =>
  aiGovernanceJsonRequest<ProviderInstallation, typeof payload>(`/api/v1/provider-installations/${encodeURIComponent(installationId)}`, { method: "PATCH", body: payload });
