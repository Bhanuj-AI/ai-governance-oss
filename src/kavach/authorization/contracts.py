"""Feature-neutral fine-grained authorization extension contract.

Core owns the authenticated tenant context and capability permission check.
Plugins may use this contract only to further constrain an operation with
resource facts supplied by the owning Core application service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from kavach.tenancy.domain import TenantContext


@dataclass(frozen=True)
class AuthorizationResourceFacts:
    resource_type: str
    resource_id: str
    organization_id: str
    project_id: str | None
    owner_id: str | None = None
    lifecycle_state: str | None = None
    environment: str | None = None
    classification: str | None = None
    version: int | None = None
    attributes: dict[str, str | int | float | bool | tuple[str | int | float | bool, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthorizationEnforcementRequest:
    context: TenantContext
    action: str
    resource: AuthorizationResourceFacts


@dataclass(frozen=True)
class AuthorizationEnforcementDecision:
    allowed: bool
    reason_code: str
    decision_id: str | None = None


class AuthorizationEnforcer(Protocol):
    """Narrow an already-authorized Core operation without granting it."""

    def authorize(
        self, request: AuthorizationEnforcementRequest
    ) -> AuthorizationEnforcementDecision: ...
