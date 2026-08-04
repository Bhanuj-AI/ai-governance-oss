from __future__ import annotations

from enum import Enum


class AssetProvenance(str, Enum):
    """How Kavach obtained an asset record.

    ``MANAGED`` records are authored or stored by Kavach, ``OBSERVED`` records
    are immutable facts reported by an execution/evaluation producer, and
    ``IMPORTED`` is reserved for a future external-registry synchronizer.
    """

    MANAGED = "MANAGED"
    OBSERVED = "OBSERVED"
    IMPORTED = "IMPORTED"
