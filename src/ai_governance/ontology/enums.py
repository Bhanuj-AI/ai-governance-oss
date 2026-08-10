from __future__ import annotations

from enum import Enum


ONTOLOGY_VERSION = "1.1.0"


class EntityType(str, Enum):
    """
    First-class entity types in the `ai_governance.governance` ontology.

    The enum values intentionally match the ontology document names so graph
    labels, relationship validation, and service APIs can share one stable
    vocabulary without depending on a storage backend.
    """

    ACTOR = "Actor"
    PROMPT = "Prompt"
    PROMPT_VERSION = "PromptVersion"
    MODEL = "Model"
    MODEL_VERSION = "ModelVersion"
    DATASET = "Dataset"
    DATASET_VERSION = "DatasetVersion"
    EVALUATION_PROVIDER = "EvaluationProvider"
    EXPERIMENT = "Experiment"
    CANDIDATE = "Candidate"
    EVALUATION_RUN = "EvaluationRun"
    EVALUATION_RESULT = "EvaluationResult"
    METRIC = "Metric"
    EVALUATION_ARTIFACT = "EvaluationArtifact"
    EVALUATION_HISTORY = "EvaluationHistory"
    EVALUATION_COMPARISON = "EvaluationComparison"
    DRIFT_ANALYSIS = "DriftAnalysis"
    LEADERBOARD = "Leaderboard"
    LEADERBOARD_ENTRY = "LeaderboardEntry"
    GOVERNANCE_DECISION = "GovernanceDecision"
    POLICY = "Policy"
    JOB = "Job"
    MCP_AUDIT_RECORD = "MCPAuditRecord"
    WORKFLOW_EXECUTION = "WorkflowExecution"
    REPLAY_INVESTIGATION = "ReplayInvestigation"
    REPLAY = "Replay"
    REPLAY_RESULT = "ReplayResult"
    GOVERNANCE_INSIGHT = "GovernanceInsight"
    GOVERNANCE_REPORT = "GovernanceReport"


class RelationshipType(str, Enum):
    """
    Directed relationship names supported by ontology version 1.0.0.

    Relationship values are used directly as Neo4j relationship type names in
    the repository adapter, so every value is an uppercase snake case token.
    """

    HAS_VERSION = "HAS_VERSION"
    VERSION_OF = "VERSION_OF"
    SUPERSEDES = "SUPERSEDES"
    OWNED_BY = "OWNED_BY"
    CREATED_BY = "CREATED_BY"
    HAS_CANDIDATE = "HAS_CANDIDATE"
    PARTICIPATES_IN = "PARTICIPATES_IN"
    USES = "USES"
    EVALUATED_BY = "EVALUATED_BY"
    HAS_RUN = "HAS_RUN"
    EXECUTES = "EXECUTES"
    PRODUCES = "PRODUCES"
    HAS_METRIC = "HAS_METRIC"
    HAS_ARTIFACT = "HAS_ARTIFACT"
    RECORDED_IN = "RECORDED_IN"
    COMPARED_WITH = "COMPARED_WITH"
    GENERATES = "GENERATES"
    CAUSED_DRIFT = "CAUSED_DRIFT"
    RANKED_BY = "RANKED_BY"
    HAS_ENTRY = "HAS_ENTRY"
    RANKS = "RANKS"
    RECOMMENDS = "RECOMMENDS"
    GENERATED_FROM = "GENERATED_FROM"
    DECIDES_ON = "DECIDES_ON"
    APPROVED_BY = "APPROVED_BY"
    REJECTED_BY = "REJECTED_BY"
    BLOCKED_BY = "BLOCKED_BY"
    GOVERNED_BY = "GOVERNED_BY"
    SUBMITTED_AS = "SUBMITTED_AS"
    RESULTED_IN = "RESULTED_IN"
    AUDITED_BY = "AUDITED_BY"
    REFERENCES_RESOURCE = "REFERENCES_RESOURCE"
    REPLAY_OF = "REPLAY_OF"
    RECONSTRUCTS = "RECONSTRUCTS"
    OBSERVED_BY = "OBSERVED_BY"
    INVESTIGATES = "INVESTIGATES"


class Cardinality(str, Enum):
    """
    Cardinality labels used by ontology relationship validation rules.

    These values describe the semantic relationship shape documented by the
    ontology. The foundation service enforces only the obvious uniqueness
    constraints in v1; the enum keeps the vocabulary stable for future graph
    schema and traversal work.
    """

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"
    ZERO_TO_MANY = "zero_to_many"
    ZERO_OR_ONE_TO_ONE = "zero_or_one_to_one"
    ZERO_OR_ONE_TO_MANY = "zero_or_one_to_many"


class EventType(str, Enum):
    """
    Semantic lifecycle events emitted by ontology-backed governance work.

    Events are stored as event records rather than graph relationships. They
    provide temporal evidence without changing the durable topology.
    """

    CREATED = "Created"
    UPDATED = "Updated"
    ACTIVATED = "Activated"
    DEPRECATED = "Deprecated"
    ARCHIVED = "Archived"
    EVALUATION_STARTED = "EvaluationStarted"
    EVALUATION_COMPLETED = "EvaluationCompleted"
    EVALUATION_FAILED = "EvaluationFailed"
    DECISION_PRODUCED = "DecisionProduced"
    REPLAY_STARTED = "ReplayStarted"
    REPLAY_COMPLETED = "ReplayCompleted"
    REPLAY_FAILED = "ReplayFailed"
    REPLAY_QUEUED = "ReplayQueued"
    REPLAY_EVALUATION_STARTED = "ReplayEvaluationStarted"
    REPLAY_EVALUATION_COMPLETED = "ReplayEvaluationCompleted"
    REPLAY_COMPARISON_STARTED = "ReplayComparisonStarted"
    REPLAY_COMPARISON_COMPLETED = "ReplayComparisonCompleted"
    REPLAY_CANCELLED = "ReplayCancelled"
    DRIFT_DETECTED = "DriftDetected"
    JOB_QUEUED = "JobQueued"
    JOB_STARTED = "JobStarted"
    JOB_SUCCEEDED = "JobSucceeded"
    JOB_FAILED = "JobFailed"
    JOB_CANCELLED = "JobCancelled"
    MCP_AUDIT_STARTED = "MCPAuditStarted"
    MCP_AUDIT_COMPLETED = "MCPAuditCompleted"
    MCP_AUDIT_FAILED = "MCPAuditFailed"
    REPORT_GENERATED = "ReportGenerated"
