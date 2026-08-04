from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict

from kavach.tenancy.domain import (
    BuiltInRole,
    MembershipStatus,
    OrganizationStatus,
    ProjectStatus,
)


class _DomainModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OrganizationResponse(_DomainModel):
    organization_id: str
    name: str
    slug: str
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime


class OrganizationCreateRequest(BaseModel):
    organization_id: str
    name: str
    slug: str


class OrganizationUpdateRequest(BaseModel):
    name: str | None = None
    slug: str | None = None


class ProjectResponse(_DomainModel):
    project_id: str
    organization_id: str
    name: str
    slug: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class ProjectCreateRequest(BaseModel):
    project_id: str
    name: str
    slug: str
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None


class MembershipResponse(_DomainModel):
    organization_id: str
    actor_id: str
    display_name: str | None
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime


class MembershipCreateRequest(BaseModel):
    actor_id: str
    display_name: str | None = None


class MembershipUpdateRequest(BaseModel):
    status: MembershipStatus


class RoleAssignmentResponse(_DomainModel):
    assignment_id: str
    organization_id: str
    project_id: str | None
    actor_id: str
    role: BuiltInRole
    created_at: datetime
    created_by: str


class RoleAssignmentCreateRequest(BaseModel):
    actor_id: str
    role: BuiltInRole
    project_id: str | None = None


class PermissionResponse(BaseModel):
    actor_id: str
    roles: list[BuiltInRole]
    permissions: list[str]
    permission_model_version: str


class ContextResponse(BaseModel):
    actor: dict[str, str | None]
    organization: dict[str, str]
    project: dict[str, str] | None
    roles: list[BuiltInRole]
    permissions: list[str]
    permission_model_version: str


class RoleDefinitionResponse(BaseModel):
    role: BuiltInRole
    permissions: list[str]
    permission_model_version: str
