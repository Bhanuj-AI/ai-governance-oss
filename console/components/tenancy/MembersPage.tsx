"use client";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Input } from "@/components/ui/input";
import { addMember, getCurrentContext, listMembers, updateMember } from "@/lib/api/tenancy";
import { OrganizationNav } from "./OrganizationNav";
import { useTenantContext } from "./TenantContextProvider";
export function MembersPage() {
  const tenant = useTenantContext(), client = useQueryClient(); const [actorId, setActorId] = useState(""), [name, setName] = useState(""), [memberView, setMemberView] = useState<"active" | "inactive">("active");
  const members = useQuery({ queryKey: ["members", tenant.organizationId], queryFn: () => listMembers(tenant.organizationId) });
  const context = useQuery({ queryKey: ["current-context", tenant.organizationId, tenant.projectId], queryFn: getCurrentContext });
  const canManage = context.data?.permissions.includes("membership.manage") ?? false;
  const activeMembers = members.data?.filter(member => member.status === "ACTIVE") ?? [];
  const inactiveMembers = members.data?.filter(member => member.status !== "ACTIVE") ?? [];
  const visibleMembers = memberView === "active" ? activeMembers : inactiveMembers;
  const refresh = () => client.invalidateQueries({ queryKey: ["members", tenant.organizationId] });
  const add = useMutation({ mutationFn: () => addMember(tenant.organizationId, { actor_id: actorId, display_name: name || undefined }), onSuccess: () => { setActorId(""); setName(""); void refresh(); } });
  const update = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => updateMember(tenant.organizationId, id, status), onSuccess: refresh });
  function submit(e: FormEvent) { e.preventDefault(); if (canManage) add.mutate(); }
  return <div className="space-y-6 p-6"><div><h1 className="text-3xl font-semibold">Members</h1><p className="mt-1 text-sm text-muted-foreground">Display names are descriptive. Actor IDs are the stable identities used for access and audit.</p></div><OrganizationNav />
    <form className="flex flex-wrap gap-2" onSubmit={submit}><Input value={actorId} onChange={e => setActorId(e.target.value)} placeholder="Actor ID" required /><Input value={name} onChange={e => setName(e.target.value)} placeholder="Display name" />
      <Button disabled={!canManage} title={!canManage ? "Requires membership.manage permission" : undefined}>Add member</Button></form>
    <div><div className="flex gap-5 border-b" role="tablist" aria-label="Member status"><button type="button" role="tab" aria-selected={memberView === "active"} onClick={() => setMemberView("active")} className={`border-b-2 px-1 pb-2 text-sm font-medium ${memberView === "active" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Active <span className="ml-1 text-xs">{activeMembers.length}</span></button><button type="button" role="tab" aria-selected={memberView === "inactive"} onClick={() => setMemberView("inactive")} className={`border-b-2 px-1 pb-2 text-sm font-medium ${memberView === "inactive" ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>Inactive <span className="ml-1 text-xs">{inactiveMembers.length}</span></button></div>
    <div className="mt-3 space-y-2">{visibleMembers.map(member => <div key={member.actor_id} className="flex flex-col gap-3 rounded-md border p-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0 space-y-1.5"><div className="flex flex-wrap items-center gap-2"><span className="font-medium">{member.display_name || "Unnamed actor"}</span><Badge variant="outline" className="text-[11px]">{member.status}</Badge></div><div className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground"><span className="shrink-0">Actor ID</span><code className="min-w-0 truncate rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground" title={member.actor_id}>{member.actor_id}</code><CopyButton value={member.actor_id} variant="ghost" size="sm" className="h-7 shrink-0 px-2" copyTitle="Copy actor ID" iconClassName="h-3.5 w-3.5" /></div></div>
      <div className="flex shrink-0 gap-2">{member.status === "ACTIVE" ? <Button variant="outline" onClick={() => update.mutate({ id: member.actor_id, status: "SUSPENDED" })}>Suspend</Button> : <Button variant="outline" onClick={() => update.mutate({ id: member.actor_id, status: "ACTIVE" })}>Reactivate</Button>}
      <Button variant="outline" onClick={() => update.mutate({ id: member.actor_id, status: "REMOVED" })}>Remove</Button></div></div>)}{!visibleMembers.length && <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">No {memberView} members.</div>}</div></div></div>;
}
