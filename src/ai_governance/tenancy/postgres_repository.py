from __future__ import annotations

from threading import RLock
import json

import psycopg  # type: ignore

from ai_governance.databases.postgres.database import PostgresDatabase

from .domain import (
    BuiltInRole,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
    Project,
    ProjectStatus,
    RoleAssignment,
)
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


class PostgresControlPlaneRepository:
    """PostgreSQL control-plane persistence with tenant-qualified reads."""

    def __init__(self, dsn: str) -> None:
        self.database = PostgresDatabase(dsn)
        self.database.initialize()
        self.lock = RLock()

    def _write(self, query: str, parameters: tuple, conflict: type[Exception]):
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(query, parameters)
                rowcount = cursor.rowcount
                connection.commit()
                return rowcount
        except psycopg.IntegrityError as exc:
            raise conflict(str(exc)) from exc

    def create_organization(self, item: Organization) -> Organization:
        self._write(
            "INSERT INTO organizations VALUES (%s,%s,%s,%s,%s,%s)",
            (
                item.organization_id,
                item.name,
                item.slug,
                item.status.value,
                item.created_at,
                item.updated_at,
            ),
            OrganizationSlugConflict,
        )
        return item

    def get_organization(self, organization_id: str) -> Organization:
        row = self._one(
            "SELECT * FROM organizations WHERE organization_id=%s", (organization_id,)
        )
        if row is None:
            raise OrganizationNotFound(organization_id)
        return self._organization(row)

    def get_organization_by_slug(self, slug: str) -> Organization:
        row = self._one("SELECT * FROM organizations WHERE slug=%s", (slug,))
        if row is None:
            raise OrganizationNotFound(slug)
        return self._organization(row)

    def list_organizations(self) -> list[Organization]:
        return [
            self._organization(row)
            for row in self._all("SELECT * FROM organizations ORDER BY created_at", ())
        ]

    def update_organization(self, item: Organization) -> Organization:
        count = self._write(
            "UPDATE organizations SET name=%s,slug=%s,status=%s,updated_at=%s WHERE organization_id=%s",
            (
                item.name,
                item.slug,
                item.status.value,
                item.updated_at,
                item.organization_id,
            ),
            OrganizationSlugConflict,
        )
        if not count:
            raise OrganizationNotFound(item.organization_id)
        return item

    def create_project(self, item: Project) -> Project:
        self._write(
            "INSERT INTO projects VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                item.project_id,
                item.organization_id,
                item.name,
                item.slug,
                item.description,
                item.status.value,
                item.created_at,
                item.updated_at,
            ),
            ProjectSlugConflict,
        )
        return item

    def get_project(self, organization_id: str, project_id: str) -> Project:
        row = self._one(
            "SELECT * FROM projects WHERE organization_id=%s AND project_id=%s",
            (organization_id, project_id),
        )
        if row is None:
            raise ProjectNotFound(project_id)
        return self._project(row)

    def list_projects(self, organization_id: str) -> list[Project]:
        self.get_organization(organization_id)
        return [
            self._project(row)
            for row in self._all(
                "SELECT * FROM projects WHERE organization_id=%s ORDER BY created_at",
                (organization_id,),
            )
        ]

    def update_project(self, item: Project) -> Project:
        count = self._write(
            "UPDATE projects SET name=%s,slug=%s,description=%s,status=%s,updated_at=%s "
            "WHERE organization_id=%s AND project_id=%s",
            (
                item.name,
                item.slug,
                item.description,
                item.status.value,
                item.updated_at,
                item.organization_id,
                item.project_id,
            ),
            ProjectSlugConflict,
        )
        if not count:
            raise ProjectNotFound(item.project_id)
        return item

    def create_membership(self, item: OrganizationMembership) -> OrganizationMembership:
        self._write(
            "INSERT INTO organization_memberships VALUES (%s,%s,%s,%s,%s,%s)",
            (
                item.organization_id,
                item.actor_id,
                item.display_name,
                item.status.value,
                item.created_at,
                item.updated_at,
            ),
            MembershipConflict,
        )
        return item

    def get_membership(
        self, organization_id: str, actor_id: str
    ) -> OrganizationMembership:
        row = self._one(
            "SELECT * FROM organization_memberships WHERE organization_id=%s AND actor_id=%s",
            (organization_id, actor_id),
        )
        if row is None:
            raise MembershipNotFound(actor_id)
        return self._membership(row)

    def list_memberships(self, organization_id: str) -> list[OrganizationMembership]:
        return [
            self._membership(row)
            for row in self._all(
                "SELECT * FROM organization_memberships WHERE organization_id=%s ORDER BY created_at",
                (organization_id,),
            )
        ]

    def update_membership(self, item: OrganizationMembership) -> OrganizationMembership:
        count = self._write(
            "UPDATE organization_memberships SET display_name=%s,status=%s,updated_at=%s "
            "WHERE organization_id=%s AND actor_id=%s",
            (
                item.display_name,
                item.status.value,
                item.updated_at,
                item.organization_id,
                item.actor_id,
            ),
            MembershipConflict,
        )
        if not count:
            raise MembershipNotFound(item.actor_id)
        return item

    def create_assignment(self, item: RoleAssignment) -> RoleAssignment:
        self._write(
            "INSERT INTO role_assignments VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                item.assignment_id,
                item.organization_id,
                item.project_id,
                item.actor_id,
                item.role.value,
                item.created_at,
                item.created_by,
            ),
            RoleAssignmentConflict,
        )
        return item

    def get_assignment(
        self, organization_id: str, assignment_id: str
    ) -> RoleAssignment:
        row = self._one(
            "SELECT * FROM role_assignments WHERE organization_id=%s AND assignment_id=%s",
            (organization_id, assignment_id),
        )
        if row is None:
            raise RoleAssignmentNotFound(assignment_id)
        return self._assignment(row)

    def list_assignments(
        self,
        organization_id: str,
        actor_id: str | None = None,
        project_id: str | None = None,
    ) -> list[RoleAssignment]:
        query = "SELECT * FROM role_assignments WHERE organization_id=%s"
        parameters: list[str] = [organization_id]
        if actor_id is not None:
            query += " AND actor_id=%s"
            parameters.append(actor_id)
        if project_id is not None:
            query += " AND (project_id IS NULL OR project_id=%s)"
            parameters.append(project_id)
        query += " ORDER BY created_at"
        return [self._assignment(row) for row in self._all(query, tuple(parameters))]

    def delete_assignment(
        self, organization_id: str, assignment_id: str
    ) -> RoleAssignment:
        item = self.get_assignment(organization_id, assignment_id)
        self._write(
            "DELETE FROM role_assignments WHERE organization_id=%s AND assignment_id=%s",
            (organization_id, assignment_id),
            RoleAssignmentConflict,
        )
        return item

    def save_authorization_audit(self, record) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO authorization_audit (organization_id, project_id, actor_id, operation, "
                "permission, authorization_result, reason_code, matched_roles_json, "
                "permission_model_version, resource_type, resource_id, request_id, correlation_id, "
                "occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)",
                (
                    record.organization_id,
                    record.project_id,
                    record.actor_id,
                    record.operation,
                    record.permission.value,
                    record.authorization_result,
                    record.reason_code.value,
                    json.dumps([role.value for role in record.matched_roles]),
                    record.permission_model_version,
                    record.resource_type,
                    record.resource_id,
                    record.request_id,
                    record.correlation_id,
                    record.occurred_at,
                ),
            )

    def _one(self, query: str, parameters: tuple):
        with self.database.connect() as connection:
            return connection.execute(query, parameters).fetchone()

    def _all(self, query: str, parameters: tuple):
        with self.database.connect() as connection:
            return connection.execute(query, parameters).fetchall()

    @staticmethod
    def _organization(row) -> Organization:
        return Organization(
            row["organization_id"],
            row["name"],
            row["slug"],
            OrganizationStatus(row["status"]),
            row["created_at"],
            row["updated_at"],
        )

    @staticmethod
    def _project(row) -> Project:
        return Project(
            row["project_id"],
            row["organization_id"],
            row["name"],
            row["slug"],
            row["description"],
            ProjectStatus(row["status"]),
            row["created_at"],
            row["updated_at"],
        )

    @staticmethod
    def _membership(row) -> OrganizationMembership:
        return OrganizationMembership(
            row["organization_id"],
            row["actor_id"],
            MembershipStatus(row["status"]),
            row["created_at"],
            row["updated_at"],
            row["display_name"],
        )

    @staticmethod
    def _assignment(row) -> RoleAssignment:
        return RoleAssignment(
            row["assignment_id"],
            row["organization_id"],
            row["project_id"],
            row["actor_id"],
            BuiltInRole(row["role"]),
            row["created_at"],
            row["created_by"],
        )
