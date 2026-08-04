from __future__ import annotations

from kavach.providers import MockEvaluationProvider
from kavach.providers.provider_metadata import ProviderDescriptorSnapshot


def test_provider_descriptor_snapshot_hash_is_deterministic() -> None:
    descriptor = MockEvaluationProvider().descriptor

    first = ProviderDescriptorSnapshot.from_descriptor(descriptor)
    second = ProviderDescriptorSnapshot.from_descriptor(descriptor)

    assert first.provider_name == "mock"
    assert first.descriptor_hash == second.descriptor_hash
    assert first.resolved_at != second.resolved_at


def test_provider_descriptor_snapshot_contains_resolved_at() -> None:
    snapshot = ProviderDescriptorSnapshot.from_descriptor(
        MockEvaluationProvider().descriptor
    )

    assert snapshot.resolved_at is not None
    assert snapshot.to_dict()["resolved_at"]


def test_provider_descriptor_snapshot_round_trips_from_dict() -> None:
    snapshot = ProviderDescriptorSnapshot.from_descriptor(
        MockEvaluationProvider().descriptor
    )

    reloaded = ProviderDescriptorSnapshot.from_dict(snapshot.to_dict())

    assert reloaded == snapshot
