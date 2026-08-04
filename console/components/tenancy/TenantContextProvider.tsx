"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

type TenantSelection = {
  organizationId: string; projectId: string; actorId: string;
  selectOrganization: (id: string) => void; selectProject: (id: string) => void;
};
const Context = createContext<TenantSelection | null>(null);
const ORG = "kavach.organization_id", PROJECT = "kavach.project_id";

export function TenantContextProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [organizationId, setOrganizationId] = useState(() =>
    typeof window === "undefined" ? "org_default" : localStorage.getItem(ORG) || "org_default");
  const [projectId, setProjectId] = useState(() =>
    typeof window === "undefined" ? "project_default" : localStorage.getItem(PROJECT) || "project_default");
  const value = useMemo(() => ({ organizationId, projectId, actorId: "local-admin",
    selectOrganization(id: string) {
      setOrganizationId(id); setProjectId(""); localStorage.setItem(ORG, id); localStorage.removeItem(PROJECT);
      window.dispatchEvent(new Event("kavach-context-change")); void queryClient.invalidateQueries();
    },
    selectProject(id: string) {
      setProjectId(id); localStorage.setItem(PROJECT, id);
      window.dispatchEvent(new Event("kavach-context-change")); void queryClient.invalidateQueries();
    },
  }), [organizationId, projectId, queryClient]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useTenantContext() {
  const value = useContext(Context); if (!value) throw new Error("TenantContextProvider is missing"); return value;
}
