from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from threading import RLock

from ai_governance.databases.sqlite.database import SQLiteDatabase

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


class SQLiteControlPlaneRepository:
    """Durable, tenant-scoped SQLite control-plane repository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.lock = RLock()
        self.database.initialize()

    def create_organization(self, item: Organization) -> Organization:
        try:
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT INTO organizations VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        item.organization_id,
                        item.name,
                        item.slug,
                        item.status.value,
                        item.created_at.isoformat(),
                        item.updated_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise OrganizationSlugConflict(item.slug) from exc
        return item

    def get_organization(self, organization_id: str) -> Organization:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM organizations WHERE organization_id = ?",
                (organization_id,),
            ).fetchone()
        if row is None:
            raise OrganizationNotFound(organization_id)
        return self._organization(row)

    def get_organization_by_slug(self, slug: str) -> Organization:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM organizations WHERE slug = ?", (slug,)
            ).fetchone()
        if row is None:
            raise OrganizationNotFound(slug)
        return self._organization(row)

    def list_organizations(self) -> list[Organization]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM organizations ORDER BY created_at"
            ).fetchall()
        return [self._organization(row) for row in rows]

    def update_organization(self, item: Organization) -> Organization:
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    "UPDATE organizations SET name=?, slug=?, status=?, updated_at=? "
                    "WHERE organization_id=?",
                    (
                        item.name,
                        item.slug,
                        item.status.value,
                        item.updated_at.isoformat(),
                        item.organization_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise OrganizationNotFound(item.organization_id)
        except sqlite3.IntegrityError as exc:
            raise OrganizationSlugConflict(item.slug) from exc
        return item

    def create_project(self, item: Project) -> Project:
        try:
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.project_id,
                        item.organization_id,
                        item.name,
                        item.slug,
                        item.description,
                        item.status.value,
                        item.created_at.isoformat(),
                        item.updated_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ProjectSlugConflict(item.slug) from exc
        return item

    def get_project(self, organization_id: str, project_id: str) -> Project:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE organization_id=? AND project_id=?",
                (organization_id, project_id),
            ).fetchone()
        if row is None:
            raise ProjectNotFound(project_id)
        return self._project(row)

    def list_projects(self, organization_id: str) -> list[Project]:
        self.get_organization(organization_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects WHERE organization_id=? ORDER BY created_at",
                (organization_id,),
            ).fetchall()
        return [self._project(row) for row in rows]

    def update_project(self, item: Project) -> Project:
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    "UPDATE projects SET name=?, slug=?, description=?, status=?, updated_at=? "
                    "WHERE organization_id=? AND project_id=?",
                    (
                        item.name,
                        item.slug,
                        item.description,
                        item.status.value,
                        item.updated_at.isoformat(),
                        item.organization_id,
                        item.project_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise ProjectNotFound(item.project_id)
        except sqlite3.IntegrityError as exc:
            raise ProjectSlugConflict(item.slug) from exc
        return item

    def create_membership(self, item: OrganizationMembership) -> OrganizationMembership:
        try:
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT INTO organization_memberships VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        item.organization_id,
                        item.actor_id,
                        item.display_name,
                        item.status.value,
                        item.created_at.isoformat(),
                        item.updated_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise MembershipConflict(item.actor_id) from exc
        return item

    def get_membership(
        self, organization_id: str, actor_id: str
    ) -> OrganizationMembership:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM organization_memberships WHERE organization_id=? AND actor_id=?",
                (organization_id, actor_id),
            ).fetchone()
        if row is None:
            raise MembershipNotFound(actor_id)
        return self._membership(row)

    def list_memberships(self, organization_id: str) -> list[OrganizationMembership]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM organization_memberships WHERE organization_id=? ORDER BY created_at",
                (organization_id,),
            ).fetchall()
        return [self._membership(row) for row in rows]

    def update_membership(self, item: OrganizationMembership) -> OrganizationMembership:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE organization_memberships SET display_name=?, status=?, updated_at=? "
                "WHERE organization_id=? AND actor_id=?",
                (
                    item.display_name,
                    item.status.value,
                    item.updated_at.isoformat(),
                    item.organization_id,
                    item.actor_id,
                ),
            )
            if cursor.rowcount == 0:
                raise MembershipNotFound(item.actor_id)
        return item

    def create_assignment(self, item: RoleAssignment) -> RoleAssignment:
        try:
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT INTO role_assignments VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.assignment_id,
                        item.organization_id,
                        item.project_id,
                        item.actor_id,
                        item.role.value,
                        item.created_at.isoformat(),
                        item.created_by,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise RoleAssignmentConflict(item.actor_id) from exc
        return item

    def get_assignment(
        self, organization_id: str, assignment_id: str
    ) -> RoleAssignment:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM role_assignments WHERE organization_id=? AND assignment_id=?",
                (organization_id, assignment_id),
            ).fetchone()
        if row is None:
            raise RoleAssignmentNotFound(assignment_id)
        return self._assignment(row)

    def list_assignments(
        self,
        organization_id: str,
        actor_id: str | None = None,
        project_id: str | None = None,
    ) -> list[RoleAssignment]:
        query = "SELECT * FROM role_assignments WHERE organization_id=?"
        parameters: list[str] = [organization_id]
        if actor_id is not None:
            query += " AND actor_id=?"
            parameters.append(actor_id)
        if project_id is not None:
            query += " AND (project_id IS NULL OR project_id=?)"
            parameters.append(project_id)
        query += " ORDER BY created_at"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._assignment(row) for row in rows]

    def delete_assignment(
        self, organization_id: str, assignment_id: str
    ) -> RoleAssignment:
        item = self.get_assignment(organization_id, assignment_id)
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM role_assignments WHERE organization_id=? AND assignment_id=?",
                (organization_id, assignment_id),
            )
        return item

    def save_authorization_audit(self, record) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO authorization_audit (organization_id, project_id, actor_id, "
                "operation, permission, authorization_result, reason_code, matched_roles_json, "
                "permission_model_version, resource_type, resource_id, request_id, correlation_id, "
                "occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.organization_id,
                    record.project_id,
                    record.actor_id,
                    record.operation,
                    record.permission.value,
                    int(record.authorization_result),
                    record.reason_code.value,
                    json.dumps([role.value for role in record.matched_roles]),
                    record.permission_model_version,
                    record.resource_type,
                    record.resource_id,
                    record.request_id,
                    record.correlation_id,
                    record.occurred_at.isoformat(),
                ),
            )

    @staticmethod
    def _organization(row) -> Organization:
        return Organization(
            row["organization_id"],
            row["name"],
            row["slug"],
            OrganizationStatus(row["status"]),
            datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["updated_at"]),
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
            datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _membership(row) -> OrganizationMembership:
        return OrganizationMembership(
            row["organization_id"],
            row["actor_id"],
            MembershipStatus(row["status"]),
            datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["updated_at"]),
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
            datetime.fromisoformat(row["created_at"]),
            row["created_by"],
        )
