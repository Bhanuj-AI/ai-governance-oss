from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any

from ai_governance.domain.experiments import Leaderboard
from ai_governance.services.experiments import RankingService


@dataclass(frozen=True)
class LeaderboardRoute:
    """
    Framework-neutral description of a leaderboard endpoint.

    Transport adapters can consume this metadata to expose the API through
    HTTP, CLI, or SDK layers without coupling AI Governance Control Plane to a specific framework.
    """

    method: str
    path: str
    handler_name: str


class LeaderboardAPI:
    """
    Framework-neutral adapter for experiment leaderboard endpoints.

    The API exposes serializable leaderboard and recommendation payloads while
    leaving ranking generation, evaluation, and deployment decisions to the
    underlying services and later transport integrations.
    """

    _ROUTES = [
        LeaderboardRoute(
            method="GET",
            path="/experiments/{experiment}/leaderboard",
            handler_name="get_leaderboard",
        ),
        LeaderboardRoute(
            method="GET",
            path="/experiments/{experiment}/leaderboard/latest",
            handler_name="get_latest_leaderboard",
        ),
        LeaderboardRoute(
            method="GET",
            path="/experiments/{experiment}/recommendation",
            handler_name="get_recommendation",
        ),
    ]

    def __init__(
        self,
        leaderboard_service: RankingService,
    ) -> None:
        """
        Create an API adapter backed by the experiment ranking service.
        """

        self._leaderboard_service = leaderboard_service

    def routes(self) -> list[LeaderboardRoute]:
        """
        Return the GET route metadata exposed by the leaderboard API.
        """

        return list(self._ROUTES)

    def get_leaderboard(
        self,
        experiment: str,
    ) -> list[dict[str, Any]]:
        """
        Return every persisted leaderboard payload for an experiment.
        """

        leaderboards = self._leaderboard_service.list_leaderboards(experiment)

        return [self._to_payload(leaderboard) for leaderboard in leaderboards]

    def get_latest_leaderboard(
        self,
        experiment: str,
    ) -> dict[str, Any] | None:
        """
        Return the most recent leaderboard payload for an experiment.
        """

        latest = self._latest_leaderboard(experiment)
        if latest is None:
            return None

        return self._to_payload(latest)

    def get_recommendation(
        self,
        experiment: str,
    ) -> dict[str, Any] | None:
        """
        Return the top-ranked candidate recommendation from the latest leaderboard.
        """

        latest = self._latest_leaderboard(experiment)
        if latest is None or not latest.entries:
            return None

        top_entry = latest.entries[0]

        return {
            "recommended_candidate_id": top_entry.candidate_id,
            "rank": top_entry.rank,
            "overall_score": top_entry.overall_score,
            "ranking_strategy": latest.ranking_strategy,
            "reason": top_entry.reason,
            "leaderboard_id": latest.leaderboard_id,
            "experiment_id": latest.experiment_id,
        }

    def _latest_leaderboard(
        self,
        experiment: str,
    ) -> Leaderboard | None:
        leaderboards = self._leaderboard_service.list_leaderboards(experiment)
        if not leaderboards:
            return None

        return max(
            leaderboards,
            key=lambda leaderboard: (
                leaderboard.generated_at,
                leaderboard.leaderboard_id,
            ),
        )

    @classmethod
    def _to_payload(
        cls,
        value: Any,
    ) -> Any:
        """
        Convert domain objects into transport-friendly Python values.

        Dataclasses become dictionaries, enums become raw values, and nested
        lists, tuples, and dictionaries are recursively normalized.
        """

        if isinstance(value, Enum):
            return value.value

        if is_dataclass(value):
            return {
                field.name: cls._to_payload(getattr(value, field.name))
                for field in fields(value)
            }

        if isinstance(value, list | tuple):
            return [cls._to_payload(item) for item in value]

        if isinstance(value, dict):
            return {key: cls._to_payload(item) for key, item in value.items()}

        return value
