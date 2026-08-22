from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_slug(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 63 or not _SLUG.fullmatch(value):
        raise ValueError(
            "slug must contain lowercase letters, numbers, and single hyphens"
        )
    return value


def utcnow() -> datetime:
    return datetime.now(UTC)


class OrganizationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class ActorType(str, Enum):
    USER = "USER"
    SERVICE = "SERVICE"
    SYSTEM = "SYSTEM"


class MembershipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REMOVED = "REMOVED"


class BuiltInRole(str, Enum):
    ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN"
    GOVERNANCE_ADMIN = "GOVERNANCE_ADMIN"
    GOVERNANCE_REVIEWER = "GOVERNANCE_REVIEWER"
    PLATFORM_OPERATOR = "PLATFORM_OPERATOR"
    VIEWER = "VIEWER"


@dataclass(frozen=True)
class Organization:
    organization_id: str
    name: str
    slug: str
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.organization_id.strip() or not self.name.strip():
            raise ValueError("organization id and name are required")
        validate_slug(self.slug)


@dataclass(frozen=True)
class Project:
    project_id: str
    organization_id: str
    name: str
    slug: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.project_id.strip()
            or not self.organization_id.strip()
            or not self.name.strip()
        ):
            raise ValueError("project id, organization id, and name are required")
        validate_slug(self.slug)


@dataclass(frozen=True)
class Actor:
    actor_id: str
    actor_type: ActorType = ActorType.USER
    display_name: str | None = None


@dataclass(frozen=True)
class OrganizationMembership:
    organization_id: str
    actor_id: str
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime
    display_name: str | None = None


@dataclass(frozen=True)
class RoleAssignment:
    assignment_id: str
    organization_id: str
    project_id: str | None
    actor_id: str
    role: BuiltInRole
    created_at: datetime
    created_by: str


@dataclass(frozen=True)
class TenantContext:
    organization_id: str
    project_id: str | None
    actor_id: str
    request_id: str
    correlation_id: str | None = None


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Immutable identity derived from a validated JWT."""

    subject: str
    principal_type: ActorType
    organization_id: str | None
    client_id: str
    issuer: str


@dataclass(frozen=True)
class AuthorizationResource:
    resource_type: str
    resource_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
