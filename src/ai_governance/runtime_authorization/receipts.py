"""Privacy-bounded runtime attestations for authorized external operations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

RUNTIME_ACTION_EXECUTION_RECEIPT_SCHEMA_VERSION = "runtime-action-execution-receipt/v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_REFERENCE_LENGTH = 512


class RuntimeActionExecutionReceiptStatus(str, Enum):
    """A runtime-reported terminal outcome for an already-authorized attempt."""

    NOT_EXECUTED = "NOT_EXECUTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RuntimeActionExecutionReceipt:
    """Immutable attestation submitted by the authenticated runtime.

    This record deliberately represents what the runtime reports.  It is not a
    claim that AIGP observed, executed, or independently proved a mutation.
    """

    receipt_id: str
    decision_id: str
    request_fingerprint: str
    action_id: str
    runtime_tool_call_id: str
    tool_arguments_digest: str
    status: RuntimeActionExecutionReceiptStatus | str
    reason_code: str
    attested_by: str
    attested_at: datetime
    result_reference: str | None = None
    result_digest: str | None = None
    supersedes_receipt_id: str | None = None
    schema_version: str = RUNTIME_ACTION_EXECUTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_ACTION_EXECUTION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("Unsupported runtime action execution receipt schema version.")
        for name, value in (
            ("receipt_id", self.receipt_id),
            ("decision_id", self.decision_id),
            ("action_id", self.action_id),
            ("runtime_tool_call_id", self.runtime_tool_call_id),
            ("reason_code", self.reason_code),
            ("attested_by", self.attested_by),
        ):
            _require_identifier(name, value)
        if not _FINGERPRINT.fullmatch(self.request_fingerprint):
            raise ValueError("request_fingerprint must be a lowercase SHA-256 hex digest.")
        _require_digest("tool_arguments_digest", self.tool_arguments_digest)
        if self.result_reference is not None and (
            not self.result_reference.strip()
            or len(self.result_reference) > _MAX_REFERENCE_LENGTH
        ):
            raise ValueError("result_reference must be non-blank and bounded.")
        if self.result_digest is not None:
            _require_digest("result_digest", self.result_digest)
        if (self.result_reference is None) != (self.result_digest is None):
            raise ValueError("result_reference and result_digest are required together.")
        if self.supersedes_receipt_id is not None:
            _require_identifier("supersedes_receipt_id", self.supersedes_receipt_id)
        if self.attested_at.tzinfo is None:
            raise ValueError("attested_at must be timezone-aware.")

        status = RuntimeActionExecutionReceiptStatus(self.status)
        if status is RuntimeActionExecutionReceiptStatus.SUCCEEDED and (
            self.result_reference is None or self.result_digest is None
        ):
            raise ValueError("SUCCEEDED receipts require a result reference and digest.")
        if status in {
            RuntimeActionExecutionReceiptStatus.NOT_EXECUTED,
            RuntimeActionExecutionReceiptStatus.UNKNOWN,
        } and self.result_reference is not None:
            raise ValueError(f"{status.value} receipts must not contain a result.")
        if status is RuntimeActionExecutionReceiptStatus.UNKNOWN and self.supersedes_receipt_id:
            raise ValueError("UNKNOWN receipts cannot supersede a prior receipt.")
        object.__setattr__(self, "status", status)

    def to_payload(self) -> Mapping[str, Any]:
        """Return the safe persistence/API shape for the append-only event."""

        return MappingProxyType(
            {
                "schema_version": self.schema_version,
                "receipt_id": self.receipt_id,
                "decision_id": self.decision_id,
                "request_fingerprint": self.request_fingerprint,
                "action_id": self.action_id,
                "runtime_tool_call_id": self.runtime_tool_call_id,
                "tool_arguments_digest": self.tool_arguments_digest,
                "status": self.status.value,
                "reason_code": self.reason_code,
                "attested_by": self.attested_by,
                "attested_at": self.attested_at.isoformat(),
                "result_reference": self.result_reference,
                "result_digest": self.result_digest,
                "supersedes_receipt_id": self.supersedes_receipt_id,
            }
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RuntimeActionExecutionReceipt:
        """Reconstruct a receipt from persisted event attributes."""

        if not isinstance(payload, Mapping):
            raise TypeError("Execution receipt payload must be a mapping.")
        try:
            return cls(
                receipt_id=str(payload["receipt_id"]),
                decision_id=str(payload["decision_id"]),
                request_fingerprint=str(payload["request_fingerprint"]),
                action_id=str(payload["action_id"]),
                runtime_tool_call_id=str(payload["runtime_tool_call_id"]),
                tool_arguments_digest=str(payload["tool_arguments_digest"]),
                status=str(payload["status"]),
                reason_code=str(payload["reason_code"]),
                attested_by=str(payload["attested_by"]),
                attested_at=datetime.fromisoformat(str(payload["attested_at"])),
                result_reference=_optional_string(payload.get("result_reference")),
                result_digest=_optional_string(payload.get("result_digest")),
                supersedes_receipt_id=_optional_string(
                    payload.get("supersedes_receipt_id")
                ),
                schema_version=str(payload["schema_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Stored runtime action execution receipt is malformed.") from exc


def _require_identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a bounded identifier.")


def _require_digest(name: str, value: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{name} must be a sha256 digest.")


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
