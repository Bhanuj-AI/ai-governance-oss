export type AIGovernanceRuntimeConfig = {
  apiBaseUrl?: string;
  keycloakUrl?: string;
  keycloakRealm?: string;
  keycloakClientId?: string;
};

declare global {
  interface Window {
    __AI_GOVERNANCE_RUNTIME_CONFIG__?: AIGovernanceRuntimeConfig;
  }
}

const buildTimeConfig: AIGovernanceRuntimeConfig = {
  apiBaseUrl: process.env.NEXT_PUBLIC_AI_GOVERNANCE_API_BASE_URL,
  keycloakUrl: process.env.NEXT_PUBLIC_KEYCLOAK_URL,
  keycloakRealm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM,
  keycloakClientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID,
};

/**
 * Returns public browser configuration injected by the Studio container at
 * startup. Build-time values remain a fallback for `pnpm dev` and for static
 * hosting, where no container entrypoint is involved.
 */
export function getAIGovernanceRuntimeConfig(): AIGovernanceRuntimeConfig {
  if (typeof window === "undefined") {
    return buildTimeConfig;
  }

  return {
    ...buildTimeConfig,
    ...window.__AI_GOVERNANCE_RUNTIME_CONFIG__,
  };
}

export function runtimeConfigValue(
  key: keyof AIGovernanceRuntimeConfig,
): string | undefined {
  return getAIGovernanceRuntimeConfig()[key]?.trim() || undefined;
}
