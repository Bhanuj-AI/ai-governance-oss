from __future__ import annotations

import ast
from pathlib import Path

from bhanuj_governance_plugin_api import (
    SPI_VERSION,
    PluginMetadata,
    ReplayExecutionResult,
    ReplayInterventionEnvelope,
)


def test_plugin_api_has_no_core_imports() -> None:
    source_root = Path(__file__).parents[1] / "src" / "bhanuj_governance_plugin_api"

    for source in source_root.glob("*.py"):
        imports = ast.parse(source.read_text()).body
        assert not any(
            isinstance(node, ast.Import)
            and any(
                alias.name == "ai_governance" or alias.name.startswith("ai_governance.")
                for alias in node.names
            )
            or isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (
                node.module == "ai_governance"
                or node.module.startswith("ai_governance.")
            )
            for node in imports
        )


def test_plugin_metadata_declares_the_supported_spi_major() -> None:
    metadata = PluginMetadata(
        name="external-runtime",
        version="1.0.0",
        required_ai_governance_version=">=1.1,<2",
    )

    assert metadata.spi_version == SPI_VERSION == "1"
    assert metadata.contract_version == "v1"


def test_governed_envelope_rejects_unknown_fields_and_raw_payload_growth() -> None:
    envelope = ReplayInterventionEnvelope(
        policy_id="policy-1",
        policy_version=1,
        external_execution_id="execution-1",
        runtime_tool_call_id="call-1",
        intervention_provider="opaque-reference",
        intervention_provider_version="v1",
        strategy="REPLACE",
        original_evidence_digest="sha256:original",
        counterfactual_reference="runtime://counterfactual",
        counterfactual_digest="sha256:counterfactual",
        intervention_digest="sha256:intervention",
    )

    payload = envelope.to_payload()

    assert ReplayInterventionEnvelope.from_payload(payload) == envelope
    try:
        ReplayInterventionEnvelope.from_payload({**payload, "raw_evidence": {}})
    except ValueError as error:
        assert "unsupported shape" in str(error)
    else:  # pragma: no cover - explicit contract guard
        raise AssertionError("Unknown envelope fields must fail closed.")


def test_external_result_is_immutable_and_has_no_core_execution_type() -> None:
    result = ReplayExecutionResult(
        execution_status="COMPLETED",
        final_state={"outcome": 0.0},
        events=({"type": "EXTERNAL_RUNTIME_REPLAY_COMPLETED"},),
    )

    assert result.final_state["outcome"] == 0.0
    assert result.events[0]["type"] == "EXTERNAL_RUNTIME_REPLAY_COMPLETED"
