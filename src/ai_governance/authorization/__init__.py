"""Generic authorization extension contracts for AI Governance Control Plane plugins."""

from .contracts import (
    AuthorizationEnforcer,
    AuthorizationEnforcementDecision,
    AuthorizationEnforcementRequest,
    AuthorizationResourceFacts,
)

__all__ = [
    "AuthorizationEnforcer",
    "AuthorizationEnforcementDecision",
    "AuthorizationEnforcementRequest",
    "AuthorizationResourceFacts",
]
