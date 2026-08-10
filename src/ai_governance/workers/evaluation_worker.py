from __future__ import annotations

import logging

from ai_governance.evaluation.evaluation_service import EvaluationService
from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.repositories.execution_repository import ExecutionRepository

logger = logging.getLogger(__name__)


class EvaluationWorker:
    """
    Executes pending workflow evaluations.

    Responsibilities
    ----------------
    - Retrieve pending workflow executions.
    - Invoke the evaluation service.
    - Persist evaluation results.

    The worker intentionally has no knowledge of:

    - evaluation providers
    - storage implementations
    - database technologies

    Dependency flow:

        ExecutionRepository
                ↓
        EvaluationWorker
                ↓
        EvaluationService
                ↓
        EvaluationProvider
                ↓
        EvaluationResult
                ↓
        EvaluationRepository
    """

    def __init__(
        self,
        execution_repository: ExecutionRepository,
        evaluation_repository: EvaluationRepository,
        evaluation_service: EvaluationService,
    ) -> None:
        self._execution_repository = execution_repository
        self._evaluation_repository = evaluation_repository
        self._evaluation_service = evaluation_service

    def run(self) -> None:
        """
        Process every pending workflow execution.

        Failures are isolated to individual executions so one bad workflow
        cannot prevent evaluation of the remaining queue.
        """

        executions = self._execution_repository.get_pending_executions()

        for execution in executions:
            try:
                evaluation_result = self._evaluation_service.evaluate(execution)

                self._evaluation_repository.save(evaluation_result)

            except Exception:
                logger.exception(
                    "Failed to evaluate execution '%s'.",
                    execution.execution_id,
                )
