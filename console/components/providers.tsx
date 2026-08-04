"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { TenantContextProvider } from "@/components/tenancy/TenantContextProvider";
import { AuthProvider } from "@/auth/auth-provider";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            staleTime: 10_000,
          },
        },
      }),
  );

  return (
    <AuthProvider>
      <QueryClientProvider client={queryClient}>
        <TenantContextProvider>{children}</TenantContextProvider>
      </QueryClientProvider>
    </AuthProvider>
  );
}
