"""Generic authorization extension contracts for AI Governance Control Plane plugins."""

from .contracts import (
    AuthorizationEnforcementDecision,
    AuthorizationEnforcementRequest,
    AuthorizationEnforcer,
    AuthorizationResourceFacts,
)

__all__ = [
    "AuthorizationEnforcementDecision",
    "AuthorizationEnforcementRequest",
    "AuthorizationEnforcer",
    "AuthorizationResourceFacts",
]
