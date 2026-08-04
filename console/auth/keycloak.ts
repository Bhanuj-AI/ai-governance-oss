import Keycloak from "keycloak-js";
import { runtimeConfigValue } from "@/lib/runtime-config";

let keycloakInstance: Keycloak | null = null;

function requiredEnvironmentVariable(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return value;
}

export function getKeycloak(): Keycloak {
  if (typeof window === "undefined") {
    throw new Error("Keycloak can only be accessed in the browser");
  }

  if (keycloakInstance) {
    return keycloakInstance;
  }

  keycloakInstance = new Keycloak({
    url: requiredEnvironmentVariable(
      "NEXT_PUBLIC_KEYCLOAK_URL",
      runtimeConfigValue("keycloakUrl"),
    ),
    realm: requiredEnvironmentVariable(
      "NEXT_PUBLIC_KEYCLOAK_REALM",
      runtimeConfigValue("keycloakRealm"),
    ),
    clientId: requiredEnvironmentVariable(
      "NEXT_PUBLIC_KEYCLOAK_CLIENT_ID",
      runtimeConfigValue("keycloakClientId"),
    ),
  });

  return keycloakInstance;
}
