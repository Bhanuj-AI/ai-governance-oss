export type AuthTokenProvider = () => Promise<string | null>;

let tokenProvider: AuthTokenProvider | null = null;

export function registerAuthTokenProvider(
  provider: AuthTokenProvider,
): () => void {
  tokenProvider = provider;

  return () => {
    if (tokenProvider === provider) {
      tokenProvider = null;
    }
  };
}

export async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") {
    return null;
  }

  return tokenProvider ? tokenProvider() : null;
}
