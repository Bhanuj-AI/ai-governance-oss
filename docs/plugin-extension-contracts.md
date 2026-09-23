# Plugin Extension Contracts

AI Governance Control Plane exposes versioned (`v1`) generic plugin contribution contracts. A
plugin registers them during `register(context)` through
`context.contributions`. Registration is single-threaded during application
construction; duplicate identities fail startup. Contributions are optional,
and an installation without plugins keeps the prior runtime behavior.

- `permissions`, `settings`, and `job_handlers` identify additions by name,
  setting key and job type respectively.
- `replay_execution_adapters` identify an external runtime by its immutable
  `adapter_id/adapter_version` name. Duplicate identities fail during plugin
  registration or worker composition; Core never imports a vendor adapter.
- Middleware is installed in ascending priority order after plugin validation.
- Health contributors run during readiness; non-UP results make readiness fail.
- Metrics providers receive the application-owned generic metric dictionary.
- Exporter failures are isolated and logged.
- Plugin lifecycle remains validate → register → start → stop, with stop in
  reverse registration order.

Plugins own their contribution implementation. AI Governance Control Plane owns registration,
ordering, lifecycle, validation, API composition and failure behavior. These
contracts intentionally contain no product-tier or vendor concepts.

## Replay Execution Adapters

An external runtime package contributes a
`ReplayExecutionAdapterContribution(adapter_id, adapter_version, adapter)` from
its `ai_governance.plugins` entry point. The adapter's `name` must exactly equal
the contributed `adapter_id/adapter_version`; the replay worker rejects any
collision with a built-in or another plugin adapter at startup.

For a governed controlled replay, the adapter receives an optional
`ReplayInterventionEnvelope` through `ReplayExecutionContext`. Its exact fields
are policy/version, external execution and tool-call IDs, intervention provider
and version, strategy, original evidence digest, counterfactual reference and
digest, and intervention digest. It intentionally contains no raw evidence,
prompt, response, tool arguments, or reasoning. The external runtime resolves
the reference and must fail closed when its content does not match the supplied
digest.

For the process-level lifecycle, including why standalone workers bootstrap
plugins and receive the generic event publisher, see
[Plugin Runtime Processes](architecture/PLUGIN_RUNTIME_PROCESSES.md).

For a plain-English introduction with lifecycle and worker sequence diagrams,
see [Plugin Extensions in Plain English](architecture/PLUGIN_EXTENSION_GUIDE.md).
