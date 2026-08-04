"""Neutral, evidence-first recommendation extension contracts."""

from __future__ import annotations

from builtins import ValueError, float
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol

from kavach.tenancy.domain import TenantContext


JsonValue = Any


class RecommendationCategory(StrEnum):
    GOVERNANCE = "GOVERNANCE"
    REPLAY = "REPLAY"
    EXPERIMENT = "EXPERIMENT"
    ROOT_CAUSE = "ROOT_CAUSE"
    OPERATIONAL = "OPERATIONAL"


class RecommendationSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecommendationConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendationActionType(StrEnum):
    VIEW_DECISION = "VIEW_DECISION"
    VIEW_ONTOLOGY = "VIEW_ONTOLOGY"
    VIEW_REPLAY = "VIEW_REPLAY"
    VIEW_EXPERIMENT = "VIEW_EXPERIMENT"
    VIEW_IMPACT_ANALYZER = "VIEW_IMPACT_ANALYZER"
    VIEW_JOB = "VIEW_JOB"
    ASK_INTELLIGENCE = "ASK_INTELLIGENCE"


class RecommendationState(StrEnum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True)
class RecommendationEvidence:
    evidence_id: str
    evidence_type: str
    source: str
    title: str
    summary: str
    entity_type: str | None = None
    entity_id: str | None = None
    metric_name: str | None = None
    metric_value: JsonValue | None = None
    deep_link: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.source or not self.title:
            raise ValueError("Recommendation evidence requires id, source, and title.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "deep_link": self.deep_link,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RecommendationAction:
    action_id: str
    label: str
    description: str
    action_type: RecommendationActionType
    target_uri: str | None
    executable: bool = False

    def __post_init__(self) -> None:
        if not self.action_id or not self.label:
            raise ValueError("Recommendation actions require id and label.")
        if self.executable:
            raise ValueError("Phase 3 recommendation actions must not be executable.")

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "action_id": self.action_id,
            "label": self.label,
            "description": self.description,
            "action_type": self.action_type.value,
            "target_uri": self.target_uri,
            "executable": False,
        }


@dataclass(frozen=True)
class RecommendationCandidate:
    recommendation_id: str
    category: RecommendationCategory
    title: str
    summary: str
    rationale: str
    severity: RecommendationSeverity
    confidence: RecommendationConfidence
    priority_score: float
    target_type: str | None
    target_id: str | None
    evidence: tuple[RecommendationEvidence, ...]
    suggested_actions: tuple[RecommendationAction, ...]
    limitations: tuple[str, ...]
    producer_id: str
    generated_at: datetime
    expires_at: datetime | None = None
    correlation_id: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.recommendation_id or not self.producer_id:
            raise ValueError("Recommendations require stable ids and a producer id.")
        if not self.evidence:
            raise ValueError("Every recommendation requires deterministic evidence.")
        if not 0 <= self.priority_score <= 100:
            raise ValueError(
                "Recommendation priority_score must be in the range 0..100."
            )
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "suggested_actions", tuple(self.suggested_actions))
        object.__setattr__(self, "limitations", tuple(self.limitations))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def with_updates(self, **values: JsonValue) -> "RecommendationCandidate":
        return replace(self, **values)

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "recommendation_id": self.recommendation_id,
            "category": self.category.value,
            "title": self.title,
            "summary": self.summary,
            "rationale": self.rationale,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "priority_score": self.priority_score,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "evidence": [item.as_dict() for item in self.evidence],
            "suggested_actions": [item.as_dict() for item in self.suggested_actions],
            "limitations": list(self.limitations),
            "producer_id": self.producer_id,
            "generated_at": self.generated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "correlation_id": self.correlation_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RecommendationContext:
    tenant_context: TenantContext
    organization_id: str
    project_id: str | None
    target_type: str | None = None
    target_id: str | None = None
    categories: frozenset[RecommendationCategory] = frozenset()
    limit: int = 20
    include_informational: bool = False

    def __post_init__(self) -> None:
        if not self.organization_id or self.limit < 1:
            raise ValueError(
                "Recommendation context requires organization_id and positive limit."
            )
        if (self.target_type is None) != (self.target_id is None):
            raise ValueError("target_type and target_id must be supplied together.")


class RecommendationProducer(Protocol):
    @property
    def producer_id(self) -> str: ...
    @property
    def categories(self) -> frozenset[RecommendationCategory]: ...
    def supports(self, context: RecommendationContext) -> bool: ...
    async def produce(
        self, context: RecommendationContext
    ) -> Sequence[RecommendationCandidate]: ...


class RecommendationPrioritizer(Protocol):
    def prioritize(
        self, candidates: Sequence[RecommendationCandidate]
    ) -> Sequence[RecommendationCandidate]: ...


class RecommendationProducerRegistry:
    """Neutral deterministic registry for read-only recommendation producers."""

    def __init__(self, producers: Sequence[RecommendationProducer] = ()) -> None:
        self._producers: dict[str, RecommendationProducer] = {}
        for producer in producers:
            self.register(producer)

    def register(self, producer: RecommendationProducer) -> None:
        if producer.producer_id in self._producers:
            raise ValueError(
                f"Recommendation producer '{producer.producer_id}' is already registered."
            )
        self._producers[producer.producer_id] = producer

    def select(
        self, context: RecommendationContext
    ) -> tuple[RecommendationProducer, ...]:
        return tuple(
            producer
            for _, producer in sorted(self._producers.items())
            if producer.supports(context)
        )

    def descriptors(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "producer_id": producer.producer_id,
                "categories": [
                    category.value for category in sorted(producer.categories, key=str)
                ],
            }
            for _, producer in sorted(self._producers.items())
        )
