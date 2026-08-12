---
name: model-runtime-capability-profile
description: Add or update a governed model-runtime capability adapter for an AI provider, model family, or API revision in AI Governance Control Plane OSS. Use when introducing support for a vendor/model's runtime parameters, endpoint contract, default values, bounds, profile version, Studio controls, or execution-parameter translation.
---

# Model Runtime Capability Profile

Add a deterministic, provider-neutral contract that lets Studio render only
valid model controls and lets candidate execution invoke the matching provider
API without relying on user guesses.

## Workflow

1. Read root `AGENTS.md`, then inspect the provider adapter and existing tests.
   Read [contract reference](references/contract.md) before changing a profile.
2. Establish the vendor-supported contract from official provider documentation
   or a reproducible integration response. Never infer support from a model
   family name alone when a version-specific rule is available.
3. Add the narrowest model-family match in
   `src/ai_governance/services/models/runtime_capability_service.py`. Give it a
   stable `profile_id` and increment `profile_version` whenever the contract
   changes.
4. Describe each portable user control with its canonical name, support flag,
   numeric type, bounds, and provider default when known. Do not include API
   keys, URLs, credentials, raw provider schemas, or undocumented controls.
5. Update the matching `ModelRuntimeAdapter` request translation. It must send
   only parameters present in persisted candidate evidence and translate
   canonical names to endpoint-specific names in one place.
6. Keep the profile immutable once a model version is registered. New evidence
   or an API change requires a new model version/profile version; never rewrite
   stored snapshots.
7. Add focused resolver, registry, execution-adapter, and REST tests. Run the
   focused checks listed in the reference.

## Rules

- Treat `DECLARED` as curated, adapter-owned knowledge. Use `VERIFIED` only
  after an explicit, authenticated verification flow records its outcome.
- Use `UNVERIFIED` for providers or model families without a reliable contract.
  Do not expose speculative fields in Studio.
- Preserve custom/provider-specific configuration as an explicit future schema
  extension, not a silent free-form invocation payload.
- Never fetch provider schemas during candidate execution. Optional discovery
  or verification happens only during registration/reverification and must not
  persist credentials.
- Preserve tenant context through registration, execution, evidence, and
  provider calls. Do not log prompt content, tokens, credentials, or raw error
  bodies.

## Done when

- Studio renders editable fields only for supported parameters and leaves blank
  values to provider defaults.
- A managed model version stores its selected profile snapshot.
- Candidate execution sends only explicit candidate overrides plus the managed
  model defaults, using the adapter's endpoint translation.
- Unsupported or incorrectly cased portable controls return a clear 400 before
  any provider invocation.
