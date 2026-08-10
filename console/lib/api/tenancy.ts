import { aiGovernanceRequest } from "./client";
import { aiGovernanceJsonRequest } from "./client";
import type { CurrentContext, Membership, Organization, Project, RoleAssignment } from "@/types/tenancy";

export const listOrganizations = () => aiGovernanceRequest<Organization[]>("/api/v1/organizations");
export const listProjects = (organizationId: string) =>
  aiGovernanceRequest<Project[]>(`/api/v1/organizations/${organizationId}/projects`);
export const getCurrentContext = () => aiGovernanceRequest<CurrentContext>("/api/v1/context");
export const listMembers = (organizationId: string) =>
  aiGovernanceRequest<Membership[]>(`/api/v1/organizations/${organizationId}/members`);
export const addMember = (organizationId: string, body: { actor_id: string; display_name?: string }) =>
  aiGovernanceJsonRequest<Membership, typeof body>(`/api/v1/organizations/${organizationId}/members`, { method: "POST", body });
export const updateMember = (organizationId: string, actorId: string, status: string) =>
  aiGovernanceJsonRequest<Membership, { status: string }>(`/api/v1/organizations/${organizationId}/members/${actorId}`, { method: "PATCH", body: { status } });
export const listRoleAssignments = (organizationId: string) =>
  aiGovernanceRequest<RoleAssignment[]>(`/api/v1/organizations/${organizationId}/role-assignments`);
export const assignRole = (organizationId: string, body: { actor_id: string; role: string; project_id?: string }) =>
  aiGovernanceJsonRequest<RoleAssignment, typeof body>(`/api/v1/organizations/${organizationId}/role-assignments`, { method: "POST", body });
export const removeRole = (organizationId: string, assignmentId: string) =>
  aiGovernanceJsonRequest<RoleAssignment, undefined>(`/api/v1/organizations/${organizationId}/role-assignments/${assignmentId}`, { method: "DELETE" });
export const createProject = (organizationId: string, body: { project_id: string; name: string; slug: string; description?: string }) =>
  aiGovernanceJsonRequest<Project, typeof body>(`/api/v1/organizations/${organizationId}/projects`, { method: "POST", body });
export const projectLifecycle = (organizationId: string, projectId: string, action: "suspend" | "activate" | "archive") =>
  aiGovernanceJsonRequest<Project, undefined>(`/api/v1/organizations/${organizationId}/projects/${projectId}/${action}`, { method: "POST" });
