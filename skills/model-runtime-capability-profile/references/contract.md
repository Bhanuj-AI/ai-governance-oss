# Runtime capability contract reference

## Ownership and flow

```text
Provider documentation / verification evidence
  -> runtime_capability_service resolver
  -> immutable ModelRuntimeCapabilitySnapshot on Model version
  -> Studio form and API validation
  -> Candidate runtime evidence
  -> ModelRuntimeAdapter endpoint request
```

`src/ai_governance/domain/models/runtime_capabilities.py` owns the durable
types. `ModelRuntimeCapabilitySnapshot` contains a stable profile identity,
version, endpoint invocation contract, verification state, and portable
parameter definitions. Its persisted value is evidence for that model version.

`src/ai_governance/services/models/runtime_capability_service.py` selects a
profile during managed model registration. Prefer a specific model-family rule
before a provider-wide fallback. Do not call external services in this resolver.

`src/ai_governance/services/candidate_execution_runtime.py` owns translation
from portable names to the provider request. For example, the portable
`max_output_tokens` becomes OpenAI's `max_completion_tokens`; do not duplicate
that mapping in Studio or experiment services.

## Add or change a profile

1. Capture the official vendor documentation URL and model/API revision in the
   pull request, without copying large provider schemas into the repository.
2. Choose a stable id such as `anthropic-messages-standard` and start at profile
   version `1`. Increment the profile version for any changed support, bounds,
   default, or invocation contract.
3. Define only portable controls the adapter can actually invoke. Current UI
   supports numeric/integer fields. Extend the domain and Studio together
   before adding other types.
4. State exact bounds/defaults where documented. If unknown, omit them rather
   than guessing.
5. Add a resolver test for the target model and a negative test for every
   unsupported portable control.
6. Add an adapter contract test asserting exact outbound parameter names and
   that absent fields are not sent.

## Compatibility

- Existing persisted models without a snapshot deserialize as
  `legacy-runtime-contract` / `UNVERIFIED` and remain readable.
- Never mutate a prior model version's snapshot. Register or create a new
  version after a provider API change.
- Observed assets retain observed configuration. They are evidence, not a
  managed contract to be rewritten.
- The registration endpoint previews a proposed contract through
  `POST /api/v1/models/runtime-capabilities/resolve`; the stored snapshot is
  authoritative after registration.

## Verification

Run at least:

```bash
uv run ruff check src/ai_governance/domain/models src/ai_governance/services/models src/ai_governance/services/candidate_execution_runtime.py
uv run pytest tests/unit/test_runtime_capability_service.py tests/unit/test_model_registry_service.py tests/unit/test_candidate_execution_runtime.py
cd console && pnpm typecheck && pnpm lint
```

For a live provider check, use a deliberately configured runtime connection,
redact all sensitive values, and capture only safe protocol metadata in logs.
