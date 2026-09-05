"use client";

import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  assignRole,
  getCurrentContext,
  listMembers,
  listRoleAssignments,
  removeRole,
} from "@/lib/api/tenancy";
import { OrganizationNav } from "./OrganizationNav";
import { useTenantContext } from "./TenantContextProvider";

const ROLES = ["ORGANIZATION_ADMIN", "GOVERNANCE_ADMIN", "GOVERNANCE_REVIEWER", "PLATFORM_OPERATOR", "VIEWER"];
const ROLE_SUMMARY: Record<string, string> = {
  ORGANIZATION_ADMIN: "Full organization and project administration",
  GOVERNANCE_ADMIN: "Policies, decisions, evaluations, and governance operations",
  GOVERNANCE_REVIEWER: "Review and publish governance policy changes",
  PLATFORM_OPERATOR: "Jobs, MCP audit, ontology operations, and platform health",
  VIEWER: "Read-only governance and platform visibility",
};
const ROLE_DETAILS: Record<string, string> = {
  ORGANIZATION_ADMIN: "Can manage organizations, projects, memberships, role assignments, policies, decisions, and platform settings.",
  GOVERNANCE_ADMIN: "Owns governance administration including policy lifecycle, decision evaluation, ontology synchronization, and governance settings.",
  GOVERNANCE_REVIEWER: "Reviews and publishes governance changes without receiving full organization administration privileges.",
  PLATFORM_OPERATOR: "Operates jobs, MCP audit workflows, ontology reconciliation, platform health, and runtime settings.",
  VIEWER: "Provides read-only access to governance, decisions, evaluations, jobs, ontology, audit, and platform health data.",
};
const PAGE_SIZE = 8;

export function AccessPage() {
  const tenant = useTenantContext();
  const client = useQueryClient();
  const [selectedActor, setSelectedActor] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [role, setRole] = useState("VIEWER");
  const [selectedRole, setSelectedRole] = useState("ORGANIZATION_ADMIN");
  const [projectScoped, setProjectScoped] = useState(true);

  const members = useQuery({
    queryKey: ["members", tenant.organizationId],
    queryFn: () => listMembers(tenant.organizationId),
  });
  const assignments = useQuery({
    queryKey: ["role-assignments", tenant.organizationId],
    queryFn: () => listRoleAssignments(tenant.organizationId),
  });
  const context = useQuery({ queryKey: ["current-context", tenant.organizationId, tenant.projectId], queryFn: getCurrentContext });
  const canManage = context.data?.permissions.includes("role_assignment.manage") ?? false;

  const filteredMembers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (members.data ?? []).filter((member) =>
      !term || [member.actor_id, member.display_name ?? "", member.status].some((value) => value.toLowerCase().includes(term)),
    );
  }, [members.data, search]);
  const pageCount = Math.max(1, Math.ceil(filteredMembers.length / PAGE_SIZE));
  const visibleMembers = filteredMembers.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const selected = (members.data ?? []).find((member) => member.actor_id === selectedActor);
  const selectedAssignments = (assignments.data ?? []).filter((item) => item.actor_id === selectedActor);

  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["role-assignments", tenant.organizationId] });
    void client.invalidateQueries({ queryKey: ["members", tenant.organizationId] });
  };
  const assign = useMutation({
    mutationFn: () => assignRole(tenant.organizationId, { actor_id: selectedActor, role, project_id: projectScoped ? tenant.projectId : undefined }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: string) => removeRole(tenant.organizationId, id), onSuccess: refresh });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (canManage && selectedActor) assign.mutate();
  }

  return (
    <div className="studio-page space-y-6">
      <div><h1 className="text-3xl font-semibold">Access</h1><p className="mt-1 text-sm text-muted-foreground">Manage actor access across the selected organization and project.</p></div>
      <OrganizationNav />

      <section className="space-y-3">
        <div><h2 className="text-lg font-semibold">Role Hiierarchy</h2><p className="text-sm text-muted-foreground">Select a role to understand its intended scope before assigning it.</p></div>
        <div className="grid gap-2 md:grid-cols-3">
          {ROLES.map((item) => <button type="button" key={item} onClick={() => setSelectedRole(item)} className={`rounded-md border p-3 text-left transition hover:border-primary ${selectedRole === item ? "border-primary bg-accent" : ""}`}><div className="text-sm font-semibold">{item.replaceAll("_", " ")}</div><p className="mt-1 text-xs text-muted-foreground">{ROLE_SUMMARY[item]}</p></button>)}
        </div>
        <div className="rounded-md border border-primary/40 bg-accent/40 p-4"><div className="text-sm font-semibold">{selectedRole.replaceAll("_", " ")}</div><p className="mt-1 text-sm text-muted-foreground">{ROLE_DETAILS[selectedRole]}</p><p className="mt-2 text-xs text-muted-foreground">Click another role card to compare its access model before assigning it.</p></div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
        <div className="space-y-3 rounded-lg border p-4">
          <div className="flex items-end justify-between gap-3"><div><h2 className="text-lg font-semibold">Actors</h2><p className="text-sm text-muted-foreground">Search and select an actor to manage their assignments.</p></div><span className="text-xs text-muted-foreground">{filteredMembers.length} actors</span></div>
          <Input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Search by name or actor ID" />
          <div className="space-y-2">
            {visibleMembers.map((member) => {
              const actorAssignments = (assignments.data ?? []).filter((item) => item.actor_id === member.actor_id);
              return <button type="button" key={member.actor_id} onClick={() => setSelectedActor(member.actor_id)} className={`w-full rounded-md border p-3 text-left transition hover:border-primary ${selectedActor === member.actor_id ? "border-primary bg-accent" : ""}`}>
                <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex items-center gap-2 truncate font-medium"><span aria-label={member.status} title={member.status} className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${member.status.toLowerCase() === "active" ? "bg-emerald-500" : "bg-slate-400"}`} />{member.display_name || "Unnamed actor"}</div><div className="truncate font-mono text-xs text-muted-foreground">{member.actor_id}</div></div><span className="rounded-full border px-2 py-0.5 text-xs">{member.status}</span></div>
                <div className="mt-2 text-xs text-muted-foreground">{actorAssignments.length} role assignment{actorAssignments.length === 1 ? "" : "s"}</div>
              </button>;
            })}
            {!visibleMembers.length && <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">No actors match this search.</div>}
          </div>
          <div className="flex items-center justify-between border-t pt-3 text-sm"><span>Page {page} of {pageCount}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</Button><Button variant="outline" size="sm" disabled={page >= pageCount} onClick={() => setPage((value) => value + 1)}>Next</Button></div></div>
        </div>

        <div className="space-y-4 rounded-lg border p-4">
          {selected ? <>
            <div><h2 className="text-lg font-semibold">Actor details</h2><p className="mt-1 flex items-center gap-2 font-medium"><span aria-label={selected.status} title={selected.status} className={`inline-block h-2.5 w-2.5 rounded-full ${selected.status.toLowerCase() === "active" ? "bg-emerald-500" : "bg-slate-400"}`} />{selected.display_name || "Unnamed actor"}</p><p className="break-all font-mono text-xs text-muted-foreground">{selected.actor_id}</p><span className="mt-2 inline-block rounded-full border px-2 py-0.5 text-xs">{selected.status}</span></div>
            <div><h3 className="mb-2 text-sm font-semibold">Current assignments</h3><div className="space-y-2">{selectedAssignments.length ? selectedAssignments.map((item) => <div key={item.assignment_id} className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm"><span><strong>{item.role}</strong><span className="ml-2 text-xs text-muted-foreground">{item.project_id || "Organization"}</span></span><Button variant="outline" size="sm" disabled={!canManage} onClick={() => remove.mutate(item.assignment_id)}>Remove</Button></div>) : <p className="text-sm text-muted-foreground">No role assignments.</p>}</div></div>
            <form className="space-y-3 border-t pt-4" onSubmit={submit}><h3 className="text-sm font-semibold">Assign role</h3><select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={role} onChange={(event) => setRole(event.target.value)}>{ROLES.map((item) => <option key={item}>{item}</option>)}</select><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={projectScoped} onChange={(event) => setProjectScoped(event.target.checked)} />Project scope ({tenant.projectId})</label><Button className="w-full" disabled={!canManage || assign.isPending} title={!canManage ? "Requires role_assignment.manage permission" : undefined}>{assign.isPending ? "Assigning..." : "Assign role"}</Button></form>
          </> : <div className="flex min-h-64 items-center justify-center text-center text-sm text-muted-foreground">Select an actor to view roles, scopes, and permissions.</div>}
        </div>
      </section>
    </div>
  );
}
