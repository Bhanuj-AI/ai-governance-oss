"use client";

import type Keycloak from "keycloak-js";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { getKeycloak } from "./keycloak";
import { registerAuthTokenProvider } from "./token-provider";

export type AuthContextValue = {
  initialized: boolean;
  authenticated: boolean;
  accessToken: string | null;
  username: string | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => Promise<string | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

let initialization: Promise<boolean> | null = null;

export function AuthProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [keycloak, setKeycloak] = useState<Keycloak | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [initializationError, setInitializationError] = useState<string | null>(
    null,
  );

  const mounted = useRef(false);
  const unregisterTokenProvider = useRef<(() => void) | null>(null);

  useEffect(() => {
    mounted.current = true;

    let instance: Keycloak;
    try {
      instance = getKeycloak();
    } catch (error) {
      console.error("Keycloak configuration failed", error);
      if (mounted.current) {
        setInitializationError(
          error instanceof Error ? error.message : "Unable to configure Keycloak",
        );
        setInitialized(true);
      }
      return () => {
        mounted.current = false;
      };
    }

    if (!initialization) {
      initialization = instance.init({
        onLoad: "login-required",
        pkceMethod: "S256",
        checkLoginIframe: false,
      });
    }

    initialization
      .then(async (isAuthenticated) => {
        if (!mounted.current) return;

        if (isAuthenticated) {
          // Ensure a session established before a Keycloak hostname/key change
          // cannot keep an old access token in memory for the first API calls.
          await instance.updateToken(-1);
        }

        unregisterTokenProvider.current?.();
        unregisterTokenProvider.current = registerAuthTokenProvider(async () => {
          if (!instance.authenticated) return null;
          try {
            await instance.updateToken(30);
            if (mounted.current) {
              const claims = instance.tokenParsed;
              setAuthenticated(Boolean(instance.authenticated));
              setAccessToken(instance.token ?? null);
              setUsername(
                friendlyDisplayName(claims),
              );
            }
            return instance.token ?? null;
          } catch (error) {
            console.error("Keycloak token refresh failed", error);
            return null;
          }
        });

        setKeycloak(instance);
        setAuthenticated(isAuthenticated);
        setAccessToken(instance.token ?? null);
        const claims = instance.tokenParsed;
        setUsername(
          friendlyDisplayName(claims),
        );
      })
      .catch((error) => {
        console.error("Keycloak initialization failed", error);
        if (mounted.current) {
          setInitializationError(
            error instanceof Error ? error.message : "Unable to initialize Keycloak",
          );
        }
      })
      .finally(() => {
        if (mounted.current) setInitialized(true);
      });

    return () => {
      mounted.current = false;
      unregisterTokenProvider.current?.();
      unregisterTokenProvider.current = null;
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    const refreshToken = async (): Promise<string | null> => {
      if (!keycloak?.authenticated) {
        return null;
      }

      try {
        await keycloak.updateToken(30);

        if (mounted.current) {
          const claims = keycloak.tokenParsed;

          setAuthenticated(Boolean(keycloak.authenticated));
          setAccessToken(keycloak.token ?? null);
          setUsername(
            friendlyDisplayName(claims),
          );
        }

        return keycloak.token ?? null;
      } catch (error) {
        console.error("Keycloak token refresh failed", error);
        return null;
      }
    };

    return {
      initialized,
      authenticated,
      accessToken,
      username,

      login: async () => {
        if (!keycloak) {
          throw new Error("Authentication has not initialized");
        }

        await keycloak.login();
      },

      logout: async () => {
        if (!keycloak) {
          return;
        }

        await keycloak.logout({
          redirectUri: window.location.origin,
        });
      },

      getAccessToken: refreshToken,
    };
  }, [accessToken, authenticated, initialized, keycloak, username]);

  if (!initialized) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        Signing in…
      </div>
    );
  }

  if (initializationError) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6 text-center">
        <div>
          <p className="font-medium">Authentication could not start.</p>
          <p className="mt-2 text-sm text-muted-foreground">{initializationError}</p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);

  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return value;
}

function friendlyDisplayName(claims: Keycloak.KeycloakTokenParsed | undefined): string | null {
  if (!claims) return null;
  const name = claims.name as string | undefined;
  const username = claims.preferred_username as string | undefined;
  const email = claims.email as string | undefined;
  const givenName = claims.given_name as string | undefined;
  const familyName = claims.family_name as string | undefined;
  return name || username || email || [givenName, familyName].filter(Boolean).join(" ") || "User";
}
