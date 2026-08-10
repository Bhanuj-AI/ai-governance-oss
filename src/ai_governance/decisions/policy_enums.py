from __future__ import annotations

from enum import Enum


class PolicyStatus(str, Enum):
    """
    Lifecycle state for a governance policy definition.
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class PolicyCategory(str, Enum):
    """
    Studio-facing category for policy administration.
    """

    SECURITY = "SECURITY"
    COMPLIANCE = "COMPLIANCE"
    DATA_QUALITY = "DATA_QUALITY"
    MODEL_RISK = "MODEL_RISK"
    PROMPT_SAFETY = "PROMPT_SAFETY"
    COST = "COST"
    OPERATIONAL_RELIABILITY = "OPERATIONAL_RELIABILITY"
    CUSTOM = "CUSTOM"


class PolicySeverity(str, Enum):
    """
    Studio-facing severity label for a policy rule.
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class PolicyEffect(str, Enum):
    """
    Decision effect produced by a matching policy rule.
    """

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    BLOCK = "BLOCK"
    RECOMMEND = "RECOMMEND"
    INVESTIGATE = "INVESTIGATE"
    NO_DECISION = "NO_DECISION"


class PolicyConditionOperator(str, Enum):
    """
    Structured comparison operators supported by policy conditions.
    """

    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    IN = "IN"
    NOT_IN = "NOT_IN"
    EXISTS = "EXISTS"
    MISSING = "MISSING"
