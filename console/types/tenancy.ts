export type Organization = { organization_id: string; name: string; slug: string; status: string };
export type Project = { project_id: string; organization_id: string; name: string; slug: string; status: string };
export type Membership = { organization_id: string; actor_id: string; display_name: string | null; status: string };
export type RoleAssignment = { assignment_id: string; organization_id: string; project_id: string | null; actor_id: string; role: string; created_by: string };
export type CurrentContext = {
  actor: { actor_id: string; actor_type: string; display_name: string | null };
  organization: { organization_id: string; name: string };
  project: { project_id: string; name: string } | null;
  roles: string[]; permissions: string[]; permission_model_version: string;
};
