"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  FolderKanban,
  ShieldCheck,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CopyButton } from "@/components/ui/copy-button";
import {
  getCurrentContext,
  listMembers,
  listProjects,
  listRoleAssignments,
} from "@/lib/api/tenancy";
import { useTenantContext } from "./TenantContextProvider";

export function OrganizationPage() {
  const tenant = useTenantContext();
  const current = useQuery({
    queryKey: ["current-context", tenant.organizationId, tenant.projectId],
    queryFn: getCurrentContext,
  });
  const projects = useQuery({
    queryKey: ["projects", tenant.organizationId],
    queryFn: () => listProjects(tenant.organizationId),
  });
  const members = useQuery({
    queryKey: ["members", tenant.organizationId],
    queryFn: () => listMembers(tenant.organizationId),
  });
  const assignments = useQuery({
    queryKey: ["role-assignments", tenant.organizationId],
    queryFn: () => listRoleAssignments(tenant.organizationId),
  });
  const selectedProject = projects.data?.find(
    (project) => project.project_id === tenant.projectId,
  );
  const directAssignments = assignments.data?.filter(
    (assignment) => assignment.project_id === selectedProject?.project_id,
  ).length ?? 0;
  const inheritedAssignments = assignments.data?.filter(
    (assignment) => assignment.project_id === null,
  ).length ?? 0;
  const activeMembers = members.data?.filter((member) => member.status === "ACTIVE").length ?? 0;

  return (
    <div className="studio-page space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-semibold">
          <Building2 className="h-6 w-6" />
          Organization
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Projects, membership, and access for the selected organization.
        </p>
      </div>
      <nav className="flex gap-2 border-b pb-3 text-sm">
        <Link className="rounded-md bg-accent px-3 py-2" href="/organization">Overview</Link>
        <Link className="rounded-md px-3 py-2 hover:bg-accent" href="/organization/projects">Projects</Link>
        <Link className="rounded-md px-3 py-2 hover:bg-accent" href="/organization/members">Members</Link>
        <Link className="rounded-md px-3 py-2 hover:bg-accent" href="/organization/access">Access</Link>
      </nav>

      <div className="grid gap-4 md:grid-cols-3">
        <Metric title="Projects" value={projects.data?.length ?? 0} icon={<FolderKanban className="h-4 w-4" />} />
        <Metric title="Effective roles" value={current.data?.roles.length ?? 0} icon={<Users className="h-4 w-4" />} />
        <Metric title="Permissions" value={current.data?.permissions.length ?? 0} icon={<ShieldCheck className="h-4 w-4" />} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Projects</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {(projects.data || []).map((project) => {
            const isSelected = project.project_id === tenant.projectId;
            return (
              <button
                key={project.project_id}
                type="button"
                onClick={() => tenant.selectProject(project.project_id)}
                className={`flex w-full items-center justify-between rounded-md border p-3 text-left transition-colors ${isSelected ? "border-primary/50 bg-primary/10" : "hover:bg-accent"}`}
                aria-pressed={isSelected}
              >
                <span>
                  <span className="font-medium">{project.name}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{project.slug}</span>
                </span>
                <span className="flex items-center gap-3 text-xs">
                  <span>{project.status}</span>
                  {isSelected ? <><CheckCircle2 className="h-4 w-4 text-primary" />Selected</> : "Select"}
                </span>
              </button>
            );
          })}
        </CardContent>
      </Card>

      {selectedProject ? (
        <Card className="border-primary/25 bg-primary/[0.03]">
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Selected project</p>
              <CardTitle className="mt-1">{selectedProject.name}</CardTitle>
            </div>
            <Badge variant="outline">{selectedProject.status}</Badge>
          </CardHeader>
          <CardContent className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            <Detail label="Project ID" value={selectedProject.project_id} copyable />
            <Detail label="Slug" value={selectedProject.slug} />
            <Detail label="Organization members" value={`${activeMembers} active`} />
            <Detail label="Role assignments" value={`${directAssignments} direct · ${inheritedAssignments} inherited`} />
            <Detail label="Your effective roles" value={`${current.data?.roles.length ?? 0} roles`} />
            <Detail label="Your permissions" value={`${current.data?.permissions.length ?? 0} permissions`} />
            <div className="md:col-span-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Operate this project</p>
              <div className="mt-2 flex gap-2 text-sm">
                <Link className="font-medium text-primary hover:underline" href="/organization/projects">Manage Lifecycle</Link>
                <Link className="font-medium text-primary hover:underline" href="/organization/access">Review Access</Link>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function Metric({ title, value, icon }: { title: string; value: number; icon: React.ReactNode }) {
  return <Card><CardHeader className="flex flex-row items-center justify-between"><CardTitle className="text-sm">{title}</CardTitle>{icon}</CardHeader>
    <CardContent className="text-2xl font-semibold">{value}</CardContent></Card>;
}

function Detail({ label, value, copyable = false }: { label: string; value: string; copyable?: boolean }) {
  return <div><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
    <div className="mt-1 flex items-center gap-1.5"><span className={copyable ? "font-mono text-sm" : "text-sm"}>{value}</span>
      {copyable ? <CopyButton value={value} variant="ghost" size="sm" className="h-7 px-1.5" copyTitle={`Copy ${label}`} iconClassName="h-3.5 w-3.5" /> : null}</div></div>;
}
