from __future__ import annotations

from dataclasses import dataclass

from kavach.domain.history import (
    EvaluationHistory,
    EvaluationHistoryRecord,
)


@dataclass(frozen=True)
class ReplayRequest:
    """
    Request object used by replay-aware governance workflows.

    The replay plane should pass this into application services instead of
    reaching into evaluation repositories directly. Keeping the request small
    gives future replay APIs room to add filters or replay metadata without
    changing the history retrieval contract.
    """

    execution_id: str


@dataclass(frozen=True)
class ReplayEvaluationHistory:
    """
    Replay-facing view of every evaluation for one workflow execution.

    This wraps the generic EvaluationHistory with the original ReplayRequest
    so replay APIs can preserve request context while exposing the familiar
    history records used by governance and reporting.
    """

    request: ReplayRequest
    history: EvaluationHistory

    @property
    def execution_id(self) -> str:
        """
        Return the execution being replayed.
        """

        return self.request.execution_id

    @property
    def evaluations(self) -> list[EvaluationHistoryRecord]:
        """
        Return all evaluation records produced for the replayed execution.
        """

        return self.history.records

    @property
    def evaluation_count(self) -> int:
        """
        Return the number of evaluations available for the replayed execution.
        """

        return self.history.evaluation_count
