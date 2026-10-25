# BHANUJ Governance Plugin API

`bhanuj-governance-plugin-api` is the small, versioned contract used to write
external runtime plugins for AI Governance Control Plane. It lets a runtime
contribute a replay adapter without importing control-plane models, services,
repositories, or workers.

It is deliberately **not** an application SDK. It does not contain a control
plane, policy evaluator, database, job worker, REST client, credentials, or
provider implementation.

## Why?

Use this package when an external runtime needs to participate in governed,
controlled replay. A LangGraph, Temporal, or proprietary runtime can privately
resolve its execution snapshot, run an isolated counterfactual, and return
bounded result evidence to the control plane.

```text
AI Governance Control Plane host ──> Plugin API <── external runtime plugin
        governance and lineage                         snapshots and execution
```

The host owns eligibility, policy authorization, replay identity, persistence,
and audit lineage. The runtime owns private snapshots, execution semantics,
isolation, retries, and recovery. The control plane is never a transaction
coordinator for the runtime's business systems.

## Install

Requires Python 3.12 or later.

```sh
pip install "bhanuj-governance-plugin-api>=1.1,<2"
```

For a plugin distribution, declare the same bounded dependency and publish an
entry point in the canonical group:

```toml
[project]
dependencies = ["bhanuj-governance-plugin-api>=1.1,<2"]

[project.entry-points."bhanuj.governance.plugins"]
my-runtime-replay = "my_runtime.plugin:MyRuntimePlugin"
```

`1.1` adds `RuntimeReplaySource/v1`. It is optional on
`ReplayExecutionContext` so existing generic replay adapters remain compatible.
When a host marks a replay as a governed runtime replay, however, it must
provide this source and the adapter must reject its absence or a mismatch.

## Public Contracts

| Contract | Responsibility |
| --- | --- |
| `PluginMetadata` | Declares plugin identity, supported host version, capabilities, and SPI major. |
| `ReplayExecutionAdapterContribution` | Registers one immutable adapter identity such as `my-runtime/v1`. |
| `ReplayExecutionContext` | Supplies host-owned replay identity, tenant scope, cancellation, governed intervention, and optional runtime source. |
| `RuntimeReplaySource` | Carries a reference-only, manifest-bound description of a governed runtime execution. |
| `ReplayInterventionEnvelope` | Carries fixed policy authorization and bounded counterfactual provenance. |
| `ReplayExecutionResult` | Returns bounded execution evidence for the host to materialise as its own record. |

The public SPI major is currently `"1"`. A plugin declares the major it
implements with `PluginMetadata(spi_version="1")`; a host rejects an unsupported
major before plugin registration.

## Minimal Plugin

The following is a minimal registration skeleton. It imports only this package;
the host discovers it through Python packaging entry points.

```python
# my_runtime/plugin.py
from bhanuj_governance_plugin_api import (
    PluginMetadata,
    ReplayExecutionAdapterContribution,
)

from my_runtime.adapter import MyRuntimeReplayAdapter
from my_runtime.snapshots import PrivateSnapshotStore


class MyRuntimePlugin:
    metadata = PluginMetadata(
        name="my-runtime-replay",
        version="0.1.0",
        required_ai_governance_version=">=1.2.4,<2",
        capabilities=("replay.execute",),
    )

    def __init__(self) -> None:
        # Runtime-owned deployment configuration. Never persist endpoints,
        # credentials, or private snapshot contents in a host artifact.
        self._snapshots = PrivateSnapshotStore.from_environment()

    def validate(self, context) -> None:
        self._snapshots.validate_configuration()

    def register(self, context) -> None:
        adapter = MyRuntimeReplayAdapter(self._snapshots)
        context.contributions.replay_execution_adapters(
            (ReplayExecutionAdapterContribution("my-runtime", "v1", adapter),)
        )

    def start(self, context) -> None:
        return None

    def stop(self, context) -> None:
        return None
```

`PrivateSnapshotStore` is runtime-owned example code, not part of this package.
The contribution identity is strict: `ReplayExecutionAdapterContribution(
"my-runtime", "v1", adapter)` requires `adapter.name == "my-runtime/v1"`.
Duplicate names fail during host startup rather than selecting an adapter
implicitly.

## Implement Replay Adapter

An adapter accepts opaque host-owned objects for the source execution and frozen
configuration. It must not import the host's corresponding implementation
types. It should use only the public context and result contracts.

```python
# my_runtime/adapter.py
from bhanuj_governance_plugin_api import (
    ReplayExecutionContext,
    ReplayExecutionResult,
    RuntimeReplaySource,
)


class MyRuntimeReplayAdapter:
    name = "my-runtime/v1"

    def __init__(self, snapshots) -> None:
        self._snapshots = snapshots

    def validate_configuration(self, source_execution, configuration) -> None:
        if getattr(configuration, "execution_adapter", None) != self.name:
            raise ValueError("Frozen configuration selected another adapter.")

    def replay(
        self,
        source_execution,
        configuration,
        context: ReplayExecutionContext,
    ) -> ReplayExecutionResult:
        self.validate_configuration(source_execution, configuration)
        if context.cancellation_token.is_cancelled:
            raise ValueError("Replay was cancelled before runtime execution.")

        source = self._require_governed_source(context.runtime_replay_source)
        envelope = context.intervention_envelope
        if envelope is None:
            raise ValueError("Controlled replay requires an intervention envelope.")
        if envelope.external_execution_id != source.external_execution_id:
            raise ValueError("The intervention belongs to another runtime execution.")

        # This method belongs to the runtime. It resolves no data through AIGP.
        snapshot = self._snapshots.resolve_and_verify(
            replay_reference=source.replay_reference,
            organization_id=context.organization_id,
            project_id=context.project_id,
            external_execution_id=source.external_execution_id,
            adapter_id=source.adapter_id,
            adapter_version=source.adapter_version,
            isolation_guarantee=source.isolation_guarantee,
            manifest_hash=source.manifest_hash,
        )

        # Run against an in-memory or otherwise isolated copy. Do not call the
        # original business system and do not retry uncertain side effects.
        score = self._run_isolated_counterfactual(
            snapshot, envelope.counterfactual_digest
        )
        outcome_reference = f"{source.replay_reference}#replay:{context.replay_id}"
        return ReplayExecutionResult(
            execution_status="COMPLETED",
            final_state={"causal_audit_outcome_score": score},
            events=(
                {
                    "type": "MY_RUNTIME_CONTROLLED_REPLAY_COMPLETED",
                    "runtime_tool_call_id": envelope.runtime_tool_call_id,
                },
            ),
            artifact_refs=(outcome_reference,),
            runtime_parameters={"isolated": True},
            metadata={
                "runtime_replay_attestation": {
                    "adapter_id": self.name,
                    "manifest_hash": source.manifest_hash,
                    "isolation_guarantee": source.isolation_guarantee,
                    "private_snapshot_integrity_verified": True,
                }
            },
        )

    def _require_governed_source(
        self, source: RuntimeReplaySource | None
    ) -> RuntimeReplaySource:
        if source is None:
            raise ValueError("Governed replay requires RuntimeReplaySource/v1.")
        if source.runtime_type != "my-runtime" or source.adapter_id != self.name:
            raise ValueError("Runtime source does not identify this adapter.")
        return source
```

`_snapshots.resolve_and_verify()` is runtime code, not part of this package. It
must retain and resolve private data entirely inside the runtime trust boundary.
The example returns a score, opaque reference, and bounded attestation only; it
does not return a snapshot, prompt, tool arguments, credentials, business
payload, model response, or hidden reasoning.

## `RuntimeReplaySource/v1`

The host creates this envelope from frozen governance evidence. An adapter
consumes it; it should not accept a caller-supplied replacement.

```python
from bhanuj_governance_plugin_api import RuntimeReplaySource

source = RuntimeReplaySource(
    source_agent_execution_id="aigp-execution-123",
    external_execution_id="runtime-run-456",
    runtime_type="my-runtime",
    adapter_id="my-runtime/v1",
    adapter_version="1",
    replay_reference="my-runtime://replays/runtime-run-456",
    isolation_guarantee="runtime-isolated/v1",
    manifest_hash="a" * 64,
)

assert source.to_payload() == {
    "schema_version": "runtime-replay-source/v1",
    "source_agent_execution_id": "aigp-execution-123",
    "external_execution_id": "runtime-run-456",
    "runtime_type": "my-runtime",
    "adapter_id": "my-runtime/v1",
    "adapter_version": "1",
    "replay_reference": "my-runtime://replays/runtime-run-456",
    "isolation_guarantee": "runtime-isolated/v1",
    "manifest_hash": "a" * 64,
}
```

The envelope contains only identities, an opaque reference, declared isolation,
and the manifest hash. Its hash is a consistency binding to the frozen AIGP
manifest; it is **not** independent proof that an external mutation occurred
or that the runtime snapshot is true. The adapter must independently verify:

1. organization and project binding;
2. external execution identity;
3. exact adapter identity and version;
4. the manifest hash and opaque reference;
5. private snapshot integrity; and
6. the declared isolation guarantee.

Unknown fields are rejected during `from_payload()` parsing. This intentionally
prevents private payloads from silently entering the public contract.

## Controlled Intervention Envelope

For governed controlled replay, `context.intervention_envelope` identifies the
policy-authorized transformation without materialising counterfactual evidence:

```python
from bhanuj_governance_plugin_api import ReplayInterventionEnvelope

intervention = ReplayInterventionEnvelope(
    policy_id="loan-status-policy",
    policy_version=3,
    external_execution_id="runtime-run-456",
    runtime_tool_call_id="loan-approval:17",
    intervention_provider="opaque-reference",
    intervention_provider_version="v1",
    strategy="REPLACE",
    original_evidence_digest="sha256:" + "b" * 64,
    counterfactual_reference="my-runtime://counterfactual/loan-17",
    counterfactual_digest="sha256:" + "c" * 64,
    intervention_digest="sha256:" + "d" * 64,
)
```

The runtime uses the reference and digest to resolve the counterfactual inside
its own boundary. It must reject unknown strategies, a mismatched execution or
tool-call identity, unresolved references, invalid digests, or a request that
cannot meet its isolation guarantee.

## Operational & Security Rules

- Treat `ReplayExecutionContext.replay_id` as the runtime replay idempotency
  key.
- Do not use controlled replay to perform an original business mutation.
- Do not automatically retry an operation with uncertain external side effects.
  Reconcile through the runtime's durable evidence instead.
- Do not place endpoints, credentials, snapshot contents, prompts, responses,
  tool arguments/results, or hidden reasoning in Plugin API objects.
- Return an authenticated runtime attestation as bounded metadata when useful,
  but do not represent it as independent proof of an external mutation.
- Fail closed when required source, intervention, tenant, identity, integrity,
  or isolation checks fail.

Adapter availability and replay eligibility are separate. Historical evidence
may be eligible even while no current worker deployment has the adapter
installed. In that case, the host should report an unavailable adapter rather
than rewriting history or bypassing the runtime boundary.

## Compatibility & Release Guidance

Existing adapters that do not implement governed runtime replay can ignore
`ReplayExecutionContext.runtime_replay_source`; the field is optional. New
adapters that declare governed runtime replay should require it. Keep adapter
identities versioned (`my-runtime/v1`) so a persisted replay configuration can
select a compatible implementation deterministically.

Before publishing a plugin:

```sh
# Build the Plugin API or your external package without local source overrides.
uv build --no-sources --wheel

# In a clean environment, install the released Plugin API and your wheel.
python -m venv /tmp/my-runtime-plugin-check
. /tmp/my-runtime-plugin-check/bin/activate
pip install "bhanuj-governance-plugin-api>=1.1,<2"
pip install dist/my_runtime_plugin-*.whl
pip check
```

Test normal completion, duplicate delivery, conflicting evidence, recovery
after an uncertain outcome, tenant forgery, adapter identity mismatch, snapshot
tampering, cancellation, and replay isolation. A plugin should be able to
perform these tests without importing `ai_governance`.

## Further Reading

- [Runtime Replay Adapter Contract](https://github.com/Bhanuj-AI/ai-governance-oss/blob/main/docs/architecture/RUNTIME_REPLAY_ADAPTER.md)
- [Plugin API architecture](https://github.com/Bhanuj-AI/ai-governance-oss/blob/main/docs/architecture/PLUGIN_API.md)
