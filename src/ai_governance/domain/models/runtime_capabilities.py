"""Immutable runtime capability contracts for governed model versions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RuntimeCapabilityVerification(str, Enum):
    """How the model runtime contract was established."""

    DECLARED = "DECLARED"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    OBSERVED = "OBSERVED"


@dataclass(frozen=True)
class RuntimeParameterCapability:
    """One provider-neutral control accepted by a model runtime contract."""

    name: str
    supported: bool
    value_type: str
    minimum: float | None = None
    maximum: float | None = None
    default: Any | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Runtime parameter capability name must not be empty.")
        if self.value_type not in {"number", "integer"}:
            raise ValueError("Runtime parameter capability type must be number or integer.")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Runtime parameter capability minimum cannot exceed maximum.")

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "supported": self.supported,
            "value_type": self.value_type,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "default": self.default,
        }

    @classmethod
    def from_record(cls, value: dict[str, Any]) -> RuntimeParameterCapability:
        return cls(
            name=str(value["name"]),
            supported=bool(value["supported"]),
            value_type=str(value["value_type"]),
            minimum=float(value["minimum"]) if value.get("minimum") is not None else None,
            maximum=float(value["maximum"]) if value.get("maximum") is not None else None,
            default=value.get("default"),
        )


@dataclass(frozen=True)
class ModelRuntimeCapabilitySnapshot:
    """Persisted, immutable provider contract selected for a model version."""

    profile_id: str
    profile_version: str
    invocation_contract: str
    verification: RuntimeCapabilityVerification
    parameters: tuple[RuntimeParameterCapability, ...]

    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.profile_version.strip():
            raise ValueError("Runtime capability profile identity must not be empty.")
        if not self.invocation_contract.strip():
            raise ValueError("Runtime capability invocation contract must not be empty.")
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("Runtime capability parameter names must be unique.")

    def supports(self, name: str) -> bool:
        return any(parameter.name == name and parameter.supported for parameter in self.parameters)

    def to_record(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "invocation_contract": self.invocation_contract,
            "verification": self.verification.value,
            "parameters": [parameter.to_record() for parameter in self.parameters],
        }

    @classmethod
    def from_record(cls, value: dict[str, Any]) -> ModelRuntimeCapabilitySnapshot:
        return cls(
            profile_id=str(value["profile_id"]),
            profile_version=str(value["profile_version"]),
            invocation_contract=str(value["invocation_contract"]),
            verification=RuntimeCapabilityVerification(str(value["verification"])),
            parameters=tuple(
                RuntimeParameterCapability.from_record(parameter)
                for parameter in value.get("parameters", [])
            ),
        )


def legacy_runtime_capability_snapshot() -> ModelRuntimeCapabilitySnapshot:
    """Represent records created before capability snapshots were introduced."""

    return ModelRuntimeCapabilitySnapshot(
        profile_id="legacy-runtime-contract",
        profile_version="0",
        invocation_contract="legacy",
        verification=RuntimeCapabilityVerification.UNVERIFIED,
        parameters=(),
    )
