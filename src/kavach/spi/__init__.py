"""Stable service-provider interfaces supported by Kavach OSS."""

from kavach.spi.context import TenantContext
from kavach.spi.evaluation import EvaluationProvider
from kavach.spi.identity import IdentityProvider
from kavach.spi.intelligence import (
    Advisor,
    AdvisorDescriptor,
    AdvisorEvidence,
    AdvisorFinding,
    AdvisorRequest,
    AdvisorSelection,
    FindingSeverity,
    FindingStatus,
    Planner,
    ReasoningPlan,
)
from kavach.spi.jobs import JobProvider
from kavach.spi.llm import LLMCompletion, LLMModelDescriptor, LLMProvider
from kavach.spi.notification import NotificationProvider
from kavach.spi.policy import PolicyProvider
from kavach.spi.ranking import RankingProvider
from kavach.spi.recommendations import (
    RecommendationAction,
    RecommendationActionType,
    RecommendationCandidate,
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationContext,
    RecommendationEvidence,
    RecommendationPrioritizer,
    RecommendationProducer,
    RecommendationProducerRegistry,
    RecommendationSeverity,
    RecommendationState,
)
from kavach.spi.search import SearchProvider, SearchRequest, SearchResult
from kavach.spi.storage import StorageProvider

__all__ = [
    "Advisor",
    "AdvisorDescriptor",
    "AdvisorEvidence",
    "AdvisorFinding",
    "AdvisorRequest",
    "AdvisorSelection",
    "EvaluationProvider",
    "FindingSeverity",
    "FindingStatus",
    "IdentityProvider",
    "JobProvider",
    "LLMCompletion",
    "LLMModelDescriptor",
    "LLMProvider",
    "NotificationProvider",
    "PolicyProvider",
    "RankingProvider",
    "SearchProvider",
    "SearchRequest",
    "Planner",
    "ReasoningPlan",
    "SearchResult",
    "StorageProvider",
    "TenantContext",
    "RecommendationAction",
    "RecommendationActionType",
    "RecommendationCandidate",
    "RecommendationCategory",
    "RecommendationConfidence",
    "RecommendationContext",
    "RecommendationEvidence",
    "RecommendationPrioritizer",
    "RecommendationProducer",
    "RecommendationProducerRegistry",
    "RecommendationSeverity",
    "RecommendationState",
]
