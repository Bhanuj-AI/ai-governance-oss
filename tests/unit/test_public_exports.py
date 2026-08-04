import kavach
from kavach import (
    AnswerRelevanceRanking,
    CandidateComparison,
    CandidateRanking,
    Dataset,
    DatasetDiff,
    DatasetRegistryService,
    DatasetStatus,
    DecisionAuditAction,
    DecisionAuditRecord,
    DecisionEvaluateCommand,
    DecisionConfidenceLevel,
    DecisionEvidenceBuilder,
    DecisionEvidenceGraph,
    DecisionEvidenceReference,
    DecisionEvidenceSummary,
    DecisionExplanation,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionStatus,
    DecisionSupersession,
    DecisionTarget,
    DecisionTargetType,
    DecisionType,
    DecisionValidationError,
    EvidenceEdge,
    EvidenceNode,
    DriftAnalyzer,
    DriftSeverity,
    EvaluationComparison,
    EvaluationArtifact,
    EvaluationDrift,
    EvaluationHistory,
    EvaluationHistoryMetric,
    EvaluationHistoryRecord,
    EvaluationHistoryService,
    EvaluationMetric,
    EvaluationMetricComparison,
    EvaluationMetricSpec,
    EvaluationMetricTrend,
    EvaluationMetricTrendPoint,
    EvaluationRun,
    EvaluationRunStatus,
    EvaluationSummary,
    EvaluationWorker,
    Experiment,
    ExperimentCandidate,
    ExperimentCandidateService,
    ExperimentEvaluationService,
    ExperimentService,
    ExperimentStatus,
    GroundednessRanking,
    HighestOverallScoreSelectionStrategy,
    HallucinationRanking,
    GovernanceDecision,
    GovernanceDecisionApplicationService,
    GovernanceDecisionRepository,
    GovernancePolicy,
    GovernancePolicyEvaluator,
    GovernancePolicyProvider,
    GovernanceReasoningEngine,
    GovernanceReasoningOutcome,
    GovernanceReasoningRequest,
    IdempotencyConflictError,
    InMemoryGovernanceDecisionRepository,
    InMemoryGovernancePolicyProvider,
    InMemoryJobRepository,
    Job,
    JobApiService,
    JobExecutor,
    JobRepository,
    JobResult,
    JobStatus,
    JobSubmission,
    JobSubmissionService,
    JobType,
    JobWorker,
    KavachMCPServer,
    Leaderboard,
    LeaderboardAPI,
    LeaderboardEntry,
    LeaderboardRoute,
    LowestCostRanking,
    LowestLatencyRanking,
    Model,
    ModelDiff,
    ModelParameterChange,
    ModelRegistryService,
    ModelStatus,
    MissingEvidence,
    OverallScoreRanking,
    PostgresGovernanceDecisionRepository,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyEvaluationContext,
    PolicyEvaluationOutcome,
    PolicyRule,
    PolicyStatus,
    ReasoningEvidenceSummarizer,
    ReasoningEvidenceSummary,
    Prompt,
    PromptDiff,
    PromptRegistryService,
    PromptStatus,
    RankingError,
    RankingService,
    RankingStrategy,
    ReplayEvaluationHistory,
    ReplayRequest,
    SQLiteGovernanceDecisionRepository,
    SQLiteJobRepository,
    WinnerSelectionStrategy,
    create_mcp_server,
)
from kavach.api import GovernanceAPI as ApiGovernanceAPI
from kavach.api import LeaderboardAPI as ApiLeaderboardAPI
from kavach.domain import Dataset as DomainDataset
from kavach.domain import DecisionAuditAction as DomainDecisionAuditAction
from kavach.domain import DecisionEvidenceBuilder as DomainDecisionEvidenceBuilder
from kavach.domain import GovernanceDecision as DomainGovernanceDecision
from kavach.domain import GovernancePolicy as DomainGovernancePolicy
from kavach.domain import GovernanceReasoningEngine as DomainReasoningEngine
from kavach.domain import EvaluationHistory as DomainEvaluationHistory
from kavach.domain import EvaluationMetric as DomainEvaluationMetric
from kavach.domain import EvaluationRun as DomainEvaluationRun
from kavach.domain import Experiment as DomainExperiment
from kavach.domain import ExperimentCandidate as DomainExperimentCandidate
from kavach.domain import Job as DomainJob
from kavach.domain import Leaderboard as DomainLeaderboard
from kavach.domain import Model as DomainModel
from kavach.domain import Prompt as DomainPrompt
from kavach.domain import ReplayRequest as DomainReplayRequest
from kavach.governance import DriftAnalyzer as GovernanceDriftAnalyzer
from kavach.services import (
    AnswerRelevanceRanking as ServicesAnswerRelevanceRanking,
)
from kavach.services import (
    GovernanceDecisionApplicationService as ServicesDecisionApplicationService,
)
from kavach.services import DatasetRegistryService as ServicesDatasetRegistryService
from kavach.services import EvaluationHistoryService as ServicesHistoryService
from kavach.services import (
    ExperimentCandidateService as ServicesExperimentCandidateService,
)
from kavach.services import (
    ExperimentEvaluationService as ServicesExperimentEvaluationService,
)
from kavach.services import ExperimentService as ServicesExperimentService
from kavach.services import GroundednessRanking as ServicesGroundednessRanking
from kavach.services import HallucinationRanking as ServicesHallucinationRanking
from kavach.services import LowestCostRanking as ServicesLowestCostRanking
from kavach.services import LowestLatencyRanking as ServicesLowestLatencyRanking
from kavach.services import ModelRegistryService as ServicesModelRegistryService
from kavach.services import OverallScoreRanking as ServicesOverallScoreRanking
from kavach.services import PromptRegistryService as ServicesPromptRegistryService
from kavach.services import RankingService as ServicesRankingService
from kavach.services import JobExecutor as ServicesJobExecutor
from kavach.services import JobApiService as ServicesJobApiService
from kavach.services import JobSubmissionService as ServicesJobSubmissionService
from kavach.mcp import KavachMCPServer as MCPServer
from kavach.mcp import create_server as create_mcp_server_impl


def test_history_api_is_exported_from_public_modules() -> None:
    assert AnswerRelevanceRanking is ServicesAnswerRelevanceRanking
    assert Dataset is DomainDataset
    assert DatasetRegistryService is ServicesDatasetRegistryService
    assert DatasetStatus.FROZEN == "FROZEN"
    assert DecisionConfidenceLevel.LOW == "LOW"
    assert DecisionAuditAction.SUPERSEDED == "SUPERSEDED"
    assert DecisionAuditRecord.__name__ == "DecisionAuditRecord"
    assert DecisionEvaluateCommand.__name__ == "DecisionEvaluateCommand"
    assert DomainDecisionAuditAction is DecisionAuditAction
    assert DecisionEvidenceBuilder is DomainDecisionEvidenceBuilder
    assert DecisionEvidenceGraph.__name__ == "DecisionEvidenceGraph"
    assert DecisionEvidenceReference.__name__ == "DecisionEvidenceReference"
    assert DecisionEvidenceSummary.__name__ == "DecisionEvidenceSummary"
    assert DecisionExplanation.__name__ == "DecisionExplanation"
    assert DecisionPolicyReference.__name__ == "DecisionPolicyReference"
    assert DecisionProducerType.POLICY_ENGINE == "POLICY_ENGINE"
    assert DecisionProvenance.__name__ == "DecisionProvenance"
    assert DecisionStatus.APPROVED == "APPROVED"
    assert DecisionSupersession.__name__ == "DecisionSupersession"
    assert DecisionTarget.__name__ == "DecisionTarget"
    assert DecisionTargetType.CANDIDATE == "Candidate"
    assert DecisionType.APPROVE == "APPROVE"
    assert DecisionValidationError.__name__ == "DecisionValidationError"
    assert EvidenceEdge.__name__ == "EvidenceEdge"
    assert EvidenceNode.__name__ == "EvidenceNode"
    assert EvaluationRun is DomainEvaluationRun
    assert EvaluationRunStatus.COMPLETED == "COMPLETED"
    assert Experiment is DomainExperiment
    assert ExperimentCandidate is DomainExperimentCandidate
    assert ExperimentCandidateService is ServicesExperimentCandidateService
    assert ExperimentEvaluationService is ServicesExperimentEvaluationService
    assert ExperimentService is ServicesExperimentService
    assert ExperimentStatus.RUNNING == "RUNNING"
    assert GroundednessRanking is ServicesGroundednessRanking
    assert HallucinationRanking is ServicesHallucinationRanking
    assert GovernanceDecision is DomainGovernanceDecision
    assert (
        GovernanceDecisionApplicationService
        is ServicesDecisionApplicationService
    )
    assert GovernanceDecisionRepository.__name__ == "GovernanceDecisionRepository"
    assert GovernancePolicy is DomainGovernancePolicy
    assert GovernancePolicyEvaluator.__name__ == "GovernancePolicyEvaluator"
    assert GovernancePolicyProvider.__name__ == "GovernancePolicyProvider"
    assert GovernanceReasoningEngine is DomainReasoningEngine
    assert GovernanceReasoningOutcome.__name__ == "GovernanceReasoningOutcome"
    assert GovernanceReasoningRequest.__name__ == "GovernanceReasoningRequest"
    assert Job is DomainJob
    assert JobApiService is ServicesJobApiService
    assert JobExecutor is ServicesJobExecutor
    assert JobSubmissionService is ServicesJobSubmissionService
    assert (
        InMemoryGovernancePolicyProvider.__name__
        == "InMemoryGovernancePolicyProvider"
    )
    assert (
        InMemoryGovernanceDecisionRepository.__name__
        == "InMemoryGovernanceDecisionRepository"
    )
    assert kavach.EvaluationHistory is EvaluationHistory
    assert kavach.GovernanceAPI is ApiGovernanceAPI
    assert kavach.LeaderboardAPI is ApiLeaderboardAPI
    assert EvaluationHistory is DomainEvaluationHistory
    assert EvaluationMetric is DomainEvaluationMetric
    assert Leaderboard is DomainLeaderboard
    assert LowestCostRanking is ServicesLowestCostRanking
    assert LowestLatencyRanking is ServicesLowestLatencyRanking
    assert DriftAnalyzer is GovernanceDriftAnalyzer
    assert EvaluationHistoryService is ServicesHistoryService
    assert Model is DomainModel
    assert ModelRegistryService is ServicesModelRegistryService
    assert ModelStatus.ACTIVE == "ACTIVE"
    assert MissingEvidence.__name__ == "MissingEvidence"
    assert OverallScoreRanking is ServicesOverallScoreRanking
    assert (
        PostgresGovernanceDecisionRepository.__name__
        == "PostgresGovernanceDecisionRepository"
    )
    assert PolicyCondition.__name__ == "PolicyCondition"
    assert PolicyConditionOperator.GREATER_THAN == "GREATER_THAN"
    assert PolicyEffect.NO_DECISION == "NO_DECISION"
    assert PolicyEvaluationContext.__name__ == "PolicyEvaluationContext"
    assert PolicyEvaluationOutcome.__name__ == "PolicyEvaluationOutcome"
    assert PolicyRule.__name__ == "PolicyRule"
    assert PolicyStatus.ACTIVE == "ACTIVE"
    assert ReasoningEvidenceSummarizer.__name__ == "ReasoningEvidenceSummarizer"
    assert ReasoningEvidenceSummary.__name__ == "ReasoningEvidenceSummary"
    assert Prompt is DomainPrompt
    assert PromptRegistryService is ServicesPromptRegistryService
    assert PromptStatus.DRAFT == "DRAFT"
    assert RankingService is ServicesRankingService
    assert DriftSeverity.HIGH == "HIGH"
    assert EvaluationComparison.__name__ == "EvaluationComparison"
    assert EvaluationArtifact.__name__ == "EvaluationArtifact"
    assert EvaluationDrift.__name__ == "EvaluationDrift"
    assert EvaluationHistoryMetric.__name__ == "EvaluationHistoryMetric"
    assert EvaluationHistoryRecord.__name__ == "EvaluationHistoryRecord"
    assert EvaluationMetricComparison.__name__ == "EvaluationMetricComparison"
    assert EvaluationMetricSpec.__name__ == "EvaluationMetricSpec"
    assert EvaluationMetricTrend.__name__ == "EvaluationMetricTrend"
    assert EvaluationMetricTrendPoint.__name__ == "EvaluationMetricTrendPoint"
    assert EvaluationSummary.__name__ == "EvaluationSummary"
    assert EvaluationWorker.__name__ == "EvaluationWorker"
    assert CandidateComparison.__name__ == "CandidateComparison"
    assert CandidateRanking.__name__ == "CandidateRanking"
    assert DatasetDiff.__name__ == "DatasetDiff"
    assert HighestOverallScoreSelectionStrategy.__name__ == "HighestOverallScoreSelectionStrategy"
    assert IdempotencyConflictError.__name__ == "IdempotencyConflictError"
    assert InMemoryJobRepository.__name__ == "InMemoryJobRepository"
    assert JobRepository.__name__ == "JobRepository"
    assert JobResult.__name__ == "JobResult"
    assert JobStatus.QUEUED == "QUEUED"
    assert JobSubmission.__name__ == "JobSubmission"
    assert JobType.EVALUATION == "EVALUATION"
    assert JobWorker.__name__ == "JobWorker"
    assert KavachMCPServer is MCPServer
    assert LeaderboardAPI.__name__ == "LeaderboardAPI"
    assert LeaderboardEntry.__name__ == "LeaderboardEntry"
    assert LeaderboardRoute.__name__ == "LeaderboardRoute"
    assert ModelDiff.__name__ == "ModelDiff"
    assert ModelParameterChange.__name__ == "ModelParameterChange"
    assert PromptDiff.__name__ == "PromptDiff"
    assert RankingError.__name__ == "RankingError"
    assert RankingStrategy.__name__ == "RankingStrategy"
    assert ReplayEvaluationHistory.__name__ == "ReplayEvaluationHistory"
    assert ReplayRequest is DomainReplayRequest
    assert (
        SQLiteGovernanceDecisionRepository.__name__
        == "SQLiteGovernanceDecisionRepository"
    )
    assert SQLiteJobRepository.__name__ == "SQLiteJobRepository"
    assert WinnerSelectionStrategy.__name__ == "WinnerSelectionStrategy"
    assert create_mcp_server is create_mcp_server_impl
