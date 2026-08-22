from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, ClassVar

from ai_governance.domain.history import EvaluationMetricComparison
from ai_governance.services.history import EvaluationHistoryService


@dataclass(frozen=True)
class GovernanceRoute:
    """
    Framework-neutral description of a governance endpoint.

    REST frameworks, CLIs, or generated documentation can consume this metadata
    without AI Governance Control Plane depending on a specific web stack.
    """

    method: str
    path: str
    handler_name: str


class GovernanceAPI:
    """
    Framework-neutral adapter for governance history endpoints.

    The class models the Phase 5 API surface without binding the project to
    FastAPI, Flask, or another server implementation. Handlers return plain
    serializable payloads that can be mounted later by any transport layer.
    """

    _ROUTES: ClassVar = [
        GovernanceRoute(
            method="GET",
            path="/history/{execution}",
            handler_name="get_history",
        ),
        GovernanceRoute(
            method="GET",
            path="/history/{execution}/latest",
            handler_name="get_latest",
        ),
        GovernanceRoute(
            method="GET",
            path="/history/{execution}/drift",
            handler_name="get_drift",
        ),
        GovernanceRoute(
            method="GET",
            path="/history/{execution}/compare",
            handler_name="get_compare",
        ),
    ]

    def __init__(
        self,
        history_service: EvaluationHistoryService,
    ) -> None:
        """
        Create an API adapter backed by an EvaluationHistoryService.
        """

        self._history_service = history_service

    def routes(self) -> list[GovernanceRoute]:
        """
        Return the GET route metadata exposed by the governance API.
        """

        return list(self._ROUTES)

    def get_history(
        self,
        execution: str,
    ) -> dict[str, Any]:
        """
        Return all evaluations recorded for an execution.
        """

        return self._to_payload(self._history_service.get_execution_history(execution))

    def get_latest(
        self,
        execution: str,
    ) -> dict[str, Any] | None:
        """
        Return the latest evaluation for an execution, if one exists.
        """

        latest = self._history_service.get_latest_evaluation(execution)

        if latest is None:
            return None

        return self._to_payload(latest)

    def get_drift(
        self,
        execution: str,
        baseline_evaluation_id: str,
        candidate_evaluation_id: str,
    ) -> dict[str, Any]:
        """
        Return governance drift between two evaluations for an execution.
        """

        return self._to_payload(
            self._history_service.analyze_drift(
                execution_id=execution,
                baseline_evaluation_id=baseline_evaluation_id,
                candidate_evaluation_id=candidate_evaluation_id,
            )
        )

    def get_compare(
        self,
        execution: str,
        baseline_evaluation_id: str,
        candidate_evaluation_id: str,
    ) -> dict[str, Any]:
        """
        Return metric-by-metric comparison for two evaluations.
        """

        return self._to_payload(
            self._history_service.compare_evaluations(
                execution_id=execution,
                baseline_evaluation_id=baseline_evaluation_id,
                candidate_evaluation_id=candidate_evaluation_id,
            )
        )

    @classmethod
    def _to_payload(
        cls,
        value: Any,
    ) -> Any:
        """
        Convert domain objects into transport-friendly Python values.

        Dataclasses are recursively converted to dictionaries, enums become
        their string values, and computed comparison properties such as
        score_difference are included explicitly.
        """

        if isinstance(value, Enum):
            return value.value

        if isinstance(value, EvaluationMetricComparison):
            payload = asdict(value)
            payload["score_difference"] = value.score_difference

            return cls._to_payload(payload)

        if is_dataclass(value):
            return {
                field.name: cls._to_payload(getattr(value, field.name))
                for field in fields(value)
            }

        if isinstance(value, list):
            return [cls._to_payload(item) for item in value]

        if isinstance(value, dict):
            return {key: cls._to_payload(item) for key, item in value.items()}

        return value
