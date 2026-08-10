"""
Tenant context factory.

Converts an AuthenticatedPrincipal into a TenantContext. Only this
component constructs TenantContext instances; REST and MCP handlers
must never construct TenantContext directly.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from .domain import AuthenticatedPrincipal, TenantContext

logger = logging.getLogger("ai_governance.tenancy.context_factory")


class TenantContextFactory:
    """
    Convert authenticated identities into tenant-scoped contexts.

    Responsibilities
    ----------------
    - Map AuthenticatedPrincipal.subject → TenantContext.actor_id
    - Propagate optional organization_id from the principal
    - Generate request_id when not provided
    - Preserve correlation_id when provided

    Never
    -----
    - Resolve memberships or permissions
    - Make authorization decisions
    - Touch the RBAC model
    """

    def create(
        self,
        principal: AuthenticatedPrincipal,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
    ) -> TenantContext:
        """
        Build a TenantContext from an authenticated principal.

        Parameters
        ----------
        principal : AuthenticatedPrincipal
            The identity established by JWT validation.
        correlation_id : str | None
            Optional correlation identifier to propagate.
        request_id : str | None
            Optional request identifier; generated if omitted.

        Returns
        -------
        TenantContext
            A tenant-scoped context ready for authorization checks.
        """
        actor_id = principal.subject
        organization_id = organization_id or principal.organization_id

        # When Keycloak provides an organization_id in the JWT, use it.
        # Otherwise the authorization layer will rely on explicit headers
        # or bootstrap defaults — this factory does not invent organization
        # membership.
        resolved_org = organization_id

        ctx = TenantContext(
            organization_id=resolved_org or "",
            project_id=project_id,
            actor_id=actor_id,
            request_id=request_id or f"req_{uuid4().hex}",
            correlation_id=correlation_id,
        )

        logger.info(
            "tenant_context_created",
            extra={
                "actor_id": actor_id,
                "organization_id": resolved_org,
                "request_id": ctx.request_id,
            },
        )

        return ctx
