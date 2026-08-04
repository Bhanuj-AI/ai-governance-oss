export type KavachRuntimeConfig = {
  apiBaseUrl?: string;
  keycloakUrl?: string;
  keycloakRealm?: string;
  keycloakClientId?: string;
};

declare global {
  interface Window {
    __KAVACH_RUNTIME_CONFIG__?: KavachRuntimeConfig;
  }
}

const buildTimeConfig: KavachRuntimeConfig = {
  apiBaseUrl: process.env.NEXT_PUBLIC_KAVACH_API_BASE_URL,
  keycloakUrl: process.env.NEXT_PUBLIC_KEYCLOAK_URL,
  keycloakRealm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM,
  keycloakClientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID,
};

/**
 * Returns public browser configuration injected by the Studio container at
 * startup. Build-time values remain a fallback for `pnpm dev` and for static
 * hosting, where no container entrypoint is involved.
 */
export function getKavachRuntimeConfig(): KavachRuntimeConfig {
  if (typeof window === "undefined") {
    return buildTimeConfig;
  }

  return {
    ...buildTimeConfig,
    ...window.__KAVACH_RUNTIME_CONFIG__,
  };
}

export function runtimeConfigValue(
  key: keyof KavachRuntimeConfig,
): string | undefined {
  return getKavachRuntimeConfig()[key]?.trim() || undefined;
}
