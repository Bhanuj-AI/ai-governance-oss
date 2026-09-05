"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createProject, getCurrentContext, listProjects, projectLifecycle } from "@/lib/api/tenancy";
import { OrganizationNav } from "./OrganizationNav";
import { useTenantContext } from "./TenantContextProvider";
import { useSearchParams } from "next/navigation";

export function ProjectsPage() {
  const tenant = useTenantContext(), client = useQueryClient();
  const searchParams = useSearchParams();
  const nameInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(""), [slug, setSlug] = useState("");
  const projects = useQuery({ queryKey: ["projects", tenant.organizationId], queryFn: () => listProjects(tenant.organizationId) });
  const context = useQuery({ queryKey: ["current-context", tenant.organizationId, tenant.projectId], queryFn: getCurrentContext });
  const canManage = context.data?.permissions.includes("project.create") ?? false;
  const refresh = () => client.invalidateQueries({ queryKey: ["projects", tenant.organizationId] });
  const create = useMutation({ mutationFn: () => createProject(tenant.organizationId,
    { project_id: `project_${crypto.randomUUID().replaceAll("-", "")}`, name, slug }), onSuccess: () => { setName(""); setSlug(""); void refresh(); } });
  const lifecycle = useMutation({ mutationFn: ({ id, action }: { id: string; action: "suspend" | "activate" | "archive" }) =>
    projectLifecycle(tenant.organizationId, id, action), onSuccess: refresh });
  useEffect(() => {
    if (searchParams.get("onboarding") === "create") nameInput.current?.focus();
  }, [searchParams]);
  function submit(event: FormEvent) { event.preventDefault(); if (canManage) create.mutate(); }
  return <div className="studio-page space-y-6"><h1 className="text-3xl font-semibold">Projects</h1><OrganizationNav />
    <form className={`flex flex-wrap gap-2 rounded-md ${searchParams.get("onboarding") === "create" ? "bg-primary/5 p-3 ring-1 ring-primary/30" : ""}`} onSubmit={submit}><Input ref={nameInput} value={name} onChange={e => setName(e.target.value)} placeholder="Project name" required />
      <Input value={slug} onChange={e => setSlug(e.target.value)} placeholder="project-slug" required />
      <Button disabled={!canManage || create.isPending} title={!canManage ? "Requires project.create permission" : undefined}>Create project</Button></form>
    <div className="space-y-2">{projects.data?.map(project => <div key={project.project_id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
      <button className="text-left" onClick={() => tenant.selectProject(project.project_id)}><span className="font-medium">{project.name}</span><span className="ml-2 text-xs text-muted-foreground">{project.status}</span></button>
      <div className="flex gap-2">{project.status === "ACTIVE" ? <Button variant="outline" onClick={() => lifecycle.mutate({ id: project.project_id, action: "suspend" })}>Suspend</Button> : null}
      {project.status === "SUSPENDED" ? <Button variant="outline" onClick={() => lifecycle.mutate({ id: project.project_id, action: "activate" })}>Activate</Button> : null}
      {project.status !== "ARCHIVED" ? <Button variant="outline" onClick={() => lifecycle.mutate({ id: project.project_id, action: "archive" })}>Archive</Button> : null}</div></div>)}</div></div>;
}
