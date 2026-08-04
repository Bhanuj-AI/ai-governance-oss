from __future__ import annotations

from enum import Enum


class DecisionType(str, Enum):
    """
    Governed outcome produced by Kavach.
    """

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    BLOCK = "BLOCK"
    RECOMMEND = "RECOMMEND"
    PROMOTE = "PROMOTE"
    ARCHIVE = "ARCHIVE"
    INVESTIGATE = "INVESTIGATE"


class DecisionStatus(str, Enum):
    """
    Lifecycle state of a governance decision.
    """

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class DecisionTargetType(str, Enum):
    """
    Ontology-aligned entity types a governance decision can target.
    """

    CANDIDATE = "Candidate"
    EXPERIMENT = "Experiment"
    PROMPT_VERSION = "PromptVersion"
    MODEL_VERSION = "ModelVersion"
    DATASET_VERSION = "DatasetVersion"
    EVALUATION_RUN = "EvaluationRun"
    EVALUATION_RESULT = "EvaluationResult"
    JOB = "Job"
    GOVERNANCE_DECISION = "GovernanceDecision"


class DecisionProducerType(str, Enum):
    """
    Kind of system or actor that produced a governance decision.
    """

    SYSTEM = "SYSTEM"
    ACTOR = "ACTOR"
    MCP_AGENT = "MCP_AGENT"
    POLICY_ENGINE = "POLICY_ENGINE"


class DecisionConfidenceLevel(str, Enum):
    """
    Confidence attached to a governance decision.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
