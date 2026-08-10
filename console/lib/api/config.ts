import { runtimeConfigValue } from "@/lib/runtime-config";

const DEFAULT_AI_GOVERNANCE_API_BASE_URL = "http://localhost:8000";

/**
 * Browser-safe API base URL.
 *
 * Next.js only auto-loads its standard `.env*` filenames. Local development
 * also uses `.env.studio`, so retain the documented local API address when the
 * public variable was not injected into the client bundle.
 */
export const AI_GOVERNANCE_API_BASE_URL = (
  runtimeConfigValue("apiBaseUrl") ||
  DEFAULT_AI_GOVERNANCE_API_BASE_URL
).replace(/\/+$/, "");
