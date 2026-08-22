from __future__ import annotations

from dataclasses import replace

from ai_governance.domain.replay import Replay
from ai_governance.domain.replay.errors import ReplayConflict, ReplayIdempotencyConflict
from ai_governance.repositories.replay_repository import (
    ReplayListFilters,
    ReplayRepository,
)


class InMemoryReplayRepository(ReplayRepository):
    """In-memory replay storage with tenant and version enforcement."""

    def __init__(self) -> None:
        self._replays: dict[str, Replay] = {}

    def save(self, replay: Replay, expected_version: int | None = None) -> Replay:
        current = self._replays.get(replay.replay_id)
        if current is None:
            if expected_version is not None:
                raise ReplayConflict("Replay does not exist for the requested update.")
            duplicate = self.find_by_idempotency(
                replay.idempotency_key,
                replay.organization_id,
                replay.project_id,
            )
            if duplicate is not None and duplicate.replay_id != replay.replay_id:
                raise ReplayIdempotencyConflict(
                    "Replay idempotency key is already in use for this project."
                )
            stored = replace(replay, version=1)
        else:
            if expected_version is None or current.version != expected_version:
                raise ReplayConflict("Replay was modified by another request.")
            if (
                current.organization_id != replay.organization_id
                or current.project_id != replay.project_id
                or current.idempotency_key != replay.idempotency_key
                or current.input_hash != replay.input_hash
            ):
                raise ReplayConflict("Immutable replay identity fields cannot change.")
            stored = replace(replay, version=current.version + 1)
        self._replays[stored.replay_id] = stored
        return stored

    def get(
        self, replay_id: str, organization_id: str, project_id: str
    ) -> Replay | None:
        replay = self._replays.get(replay_id)
        if replay is None:
            return None
        if replay.organization_id != organization_id or replay.project_id != project_id:
            return None
        return replay

    def list(
        self,
        filters: ReplayListFilters,
        organization_id: str,
        project_id: str,
    ) -> list[Replay]:
        results = [
            replay
            for replay in self._replays.values()
            if replay.organization_id == organization_id
            and replay.project_id == project_id
            and (filters.status is None or replay.status is filters.status)
            and (
                filters.source_execution_id is None
                or replay.source_execution_id == filters.source_execution_id
            )
            and (
                filters.requested_by is None
                or replay.requested_by == filters.requested_by
            )
            and (
                filters.created_after is None
                or replay.created_at >= filters.created_after
            )
            and (
                filters.created_before is None
                or replay.created_at <= filters.created_before
            )
        ]
        return sorted(
            results,
            key=lambda replay: (replay.created_at, replay.replay_id),
            reverse=True,
        )[: filters.limit]

    def find_by_idempotency(
        self,
        idempotency_key: str,
        organization_id: str,
        project_id: str,
    ) -> Replay | None:
        return next(
            (
                replay
                for replay in self._replays.values()
                if replay.idempotency_key == idempotency_key
                and replay.organization_id == organization_id
                and replay.project_id == project_id
            ),
            None,
        )

    def update(self, replay: Replay, expected_version: int) -> Replay:
        return self.save(replay, expected_version)

    def archive(self, replay: Replay, expected_version: int) -> Replay:
        return self.save(replay, expected_version)
