import { kavachRequest } from "./client";
import { kavachJsonRequest } from "./client";
import type { CurrentContext, Membership, Organization, Project, RoleAssignment } from "@/types/tenancy";

export const listOrganizations = () => kavachRequest<Organization[]>("/api/v1/organizations");
export const listProjects = (organizationId: string) =>
  kavachRequest<Project[]>(`/api/v1/organizations/${organizationId}/projects`);
export const getCurrentContext = () => kavachRequest<CurrentContext>("/api/v1/context");
export const listMembers = (organizationId: string) =>
  kavachRequest<Membership[]>(`/api/v1/organizations/${organizationId}/members`);
export const addMember = (organizationId: string, body: { actor_id: string; display_name?: string }) =>
  kavachJsonRequest<Membership, typeof body>(`/api/v1/organizations/${organizationId}/members`, { method: "POST", body });
export const updateMember = (organizationId: string, actorId: string, status: string) =>
  kavachJsonRequest<Membership, { status: string }>(`/api/v1/organizations/${organizationId}/members/${actorId}`, { method: "PATCH", body: { status } });
export const listRoleAssignments = (organizationId: string) =>
  kavachRequest<RoleAssignment[]>(`/api/v1/organizations/${organizationId}/role-assignments`);
export const assignRole = (organizationId: string, body: { actor_id: string; role: string; project_id?: string }) =>
  kavachJsonRequest<RoleAssignment, typeof body>(`/api/v1/organizations/${organizationId}/role-assignments`, { method: "POST", body });
export const removeRole = (organizationId: string, assignmentId: string) =>
  kavachJsonRequest<RoleAssignment, undefined>(`/api/v1/organizations/${organizationId}/role-assignments/${assignmentId}`, { method: "DELETE" });
export const createProject = (organizationId: string, body: { project_id: string; name: string; slug: string; description?: string }) =>
  kavachJsonRequest<Project, typeof body>(`/api/v1/organizations/${organizationId}/projects`, { method: "POST", body });
export const projectLifecycle = (organizationId: string, projectId: string, action: "suspend" | "activate" | "archive") =>
  kavachJsonRequest<Project, undefined>(`/api/v1/organizations/${organizationId}/projects/${projectId}/${action}`, { method: "POST" });
