import { aiGovernanceJsonRequest, aiGovernanceRequest } from "@/lib/api/client";

type DemoSeedResponse = {
  seeded: boolean;
  decision_ids: string[];
};

export type AgentRuntimeDemoStatus = {
  seeded: boolean;
};

/** Seed the idempotent, full workflow fixture used by the local Studio mentor. */
export const seedLocalDemoData = () =>
  aiGovernanceJsonRequest<DemoSeedResponse, undefined>("/api/v1/local/demo/seed", {
    method: "POST",
  });

/** Seed agent runtime demo data — executions and findings. */
export const seedAgentRuntimeDemo = () =>
  aiGovernanceJsonRequest<DemoSeedResponse, undefined>(
    "/api/v1/local/demo/agent-runtime",
    { method: "POST" },
  );

/** Read whether the complete local Agent Runtime sample is already available. */
export const getAgentRuntimeDemoStatus = () =>
  aiGovernanceRequest<AgentRuntimeDemoStatus>(
    "/api/v1/local/demo/agent-runtime/status",
  );
