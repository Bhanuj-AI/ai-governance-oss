"""Generic authorization extension contracts for Kavach plugins."""

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
