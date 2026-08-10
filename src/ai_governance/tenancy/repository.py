from __future__ import annotations

from threading import RLock
from typing import Protocol

from .domain import Organization, OrganizationMembership, Project, RoleAssignment
from .errors import (
    MembershipConflict,
    MembershipNotFound,
    OrganizationNotFound,
    OrganizationSlugConflict,
    ProjectNotFound,
    ProjectSlugConflict,
    RoleAssignmentConflict,
    RoleAssignmentNotFound,
)


class OrganizationRepository(Protocol):
    def create_organization(self, organization: Organization) -> Organization: ...
    def get_organization(self, organization_id: str) -> Organization: ...
    def get_organization_by_slug(self, slug: str) -> Organization: ...
    def list_organizations(self) -> list[Organization]: ...
    def update_organization(self, organization: Organization) -> Organization: ...


class ProjectRepository(Protocol):
    def create_project(self, project: Project) -> Project: ...
    def get_project(self, organization_id: str, project_id: str) -> Project: ...
    def list_projects(self, organization_id: str) -> list[Project]: ...
    def update_project(self, project: Project) -> Project: ...


class MembershipRepository(Protocol):
    def create_membership(
        self, membership: OrganizationMembership
    ) -> OrganizationMembership: ...
    def get_membership(
        self, organization_id: str, actor_id: str
    ) -> OrganizationMembership: ...
    def list_memberships(
        self, organization_id: str
    ) -> list[OrganizationMembership]: ...
    def update_membership(
        self, membership: OrganizationMembership
    ) -> OrganizationMembership: ...


class RoleAssignmentRepository(Protocol):
    def create_assignment(self, assignment: RoleAssignment) -> RoleAssignment: ...
    def get_assignment(
        self, organization_id: str, assignment_id: str
    ) -> RoleAssignment: ...
    def list_assignments(
        self,
        organization_id: str,
        actor_id: str | None = None,
        project_id: str | None = None,
    ) -> list[RoleAssignment]: ...
    def delete_assignment(
        self, organization_id: str, assignment_id: str
    ) -> RoleAssignment: ...


class InMemoryControlPlaneRepository:
    """Atomic in-memory control-plane store used by local development and tests."""

    def __init__(self) -> None:
        self._organizations: dict[str, Organization] = {}
        self._projects: dict[tuple[str, str], Project] = {}
        self._memberships: dict[tuple[str, str], OrganizationMembership] = {}
        self._assignments: dict[str, RoleAssignment] = {}
        self.authorization_audit_records: list[object] = []
        self.lock = RLock()

    def create_organization(self, organization: Organization) -> Organization:
        with self.lock:
            if organization.organization_id in self._organizations or any(
                item.slug == organization.slug for item in self._organizations.values()
            ):
                raise OrganizationSlugConflict(organization.slug)
            self._organizations[organization.organization_id] = organization
            return organization

    def get_organization(self, organization_id: str) -> Organization:
        try:
            return self._organizations[organization_id]
        except KeyError as exc:
            raise OrganizationNotFound(organization_id) from exc

    def get_organization_by_slug(self, slug: str) -> Organization:
        for item in self._organizations.values():
            if item.slug == slug:
                return item
        raise OrganizationNotFound(slug)

    def list_organizations(self) -> list[Organization]:
        return sorted(self._organizations.values(), key=lambda item: item.created_at)

    def update_organization(self, organization: Organization) -> Organization:
        with self.lock:
            self.get_organization(organization.organization_id)
            if any(
                item.slug == organization.slug
                and item.organization_id != organization.organization_id
                for item in self._organizations.values()
            ):
                raise OrganizationSlugConflict(organization.slug)
            self._organizations[organization.organization_id] = organization
            return organization

    def create_project(self, project: Project) -> Project:
        with self.lock:
            self.get_organization(project.organization_id)
            key = (project.organization_id, project.project_id)
            if key in self._projects or any(
                item.organization_id == project.organization_id
                and item.slug == project.slug
                for item in self._projects.values()
            ):
                raise ProjectSlugConflict(project.slug)
            self._projects[key] = project
            return project

    def get_project(self, organization_id: str, project_id: str) -> Project:
        try:
            return self._projects[(organization_id, project_id)]
        except KeyError as exc:
            raise ProjectNotFound(project_id) from exc

    def list_projects(self, organization_id: str) -> list[Project]:
        self.get_organization(organization_id)
        return sorted(
            (
                item
                for item in self._projects.values()
                if item.organization_id == organization_id
            ),
            key=lambda item: item.created_at,
        )

    def update_project(self, project: Project) -> Project:
        with self.lock:
            self.get_project(project.organization_id, project.project_id)
            if any(
                item.organization_id == project.organization_id
                and item.slug == project.slug
                and item.project_id != project.project_id
                for item in self._projects.values()
            ):
                raise ProjectSlugConflict(project.slug)
            self._projects[(project.organization_id, project.project_id)] = project
            return project

    def create_membership(
        self, membership: OrganizationMembership
    ) -> OrganizationMembership:
        with self.lock:
            self.get_organization(membership.organization_id)
            key = (membership.organization_id, membership.actor_id)
            if key in self._memberships:
                raise MembershipConflict(membership.actor_id)
            self._memberships[key] = membership
            return membership

    def get_membership(
        self, organization_id: str, actor_id: str
    ) -> OrganizationMembership:
        try:
            return self._memberships[(organization_id, actor_id)]
        except KeyError as exc:
            raise MembershipNotFound(actor_id) from exc

    def list_memberships(self, organization_id: str) -> list[OrganizationMembership]:
        return [
            item
            for item in self._memberships.values()
            if item.organization_id == organization_id
        ]

    def update_membership(
        self, membership: OrganizationMembership
    ) -> OrganizationMembership:
        with self.lock:
            self.get_membership(membership.organization_id, membership.actor_id)
            self._memberships[(membership.organization_id, membership.actor_id)] = (
                membership
            )
            return membership

    def create_assignment(self, assignment: RoleAssignment) -> RoleAssignment:
        with self.lock:
            self.get_membership(assignment.organization_id, assignment.actor_id)
            if assignment.project_id is not None:
                self.get_project(assignment.organization_id, assignment.project_id)
            if any(
                item.organization_id == assignment.organization_id
                and item.project_id == assignment.project_id
                and item.actor_id == assignment.actor_id
                and item.role == assignment.role
                for item in self._assignments.values()
            ):
                raise RoleAssignmentConflict(assignment.actor_id)
            self._assignments[assignment.assignment_id] = assignment
            return assignment

    def get_assignment(
        self, organization_id: str, assignment_id: str
    ) -> RoleAssignment:
        item = self._assignments.get(assignment_id)
        if item is None or item.organization_id != organization_id:
            raise RoleAssignmentNotFound(assignment_id)
        return item

    def list_assignments(
        self,
        organization_id: str,
        actor_id: str | None = None,
        project_id: str | None = None,
    ) -> list[RoleAssignment]:
        return [
            item
            for item in self._assignments.values()
            if item.organization_id == organization_id
            and (actor_id is None or item.actor_id == actor_id)
            and (project_id is None or item.project_id in {None, project_id})
        ]

    def delete_assignment(
        self, organization_id: str, assignment_id: str
    ) -> RoleAssignment:
        with self.lock:
            item = self.get_assignment(organization_id, assignment_id)
            del self._assignments[assignment_id]
            return item

    def save_authorization_audit(self, record: object) -> None:
        self.authorization_audit_records.append(record)
