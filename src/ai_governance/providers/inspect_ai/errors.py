"""Inspect adapter errors safe to expose at the provider boundary."""


class InspectRunnerError(ValueError):
    """Raised when Inspect cannot execute or normalize an evaluation run."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "evaluation_runner_failure",
    ) -> None:
        self.category = category
        super().__init__(f"[{category}] {message}")
