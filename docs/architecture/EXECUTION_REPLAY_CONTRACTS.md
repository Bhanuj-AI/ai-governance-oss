# Execution Replay Contracts

## Status and Ownership

This document describes the Phase 2 Plugin API contracts and resolution
engine. They are vendor-neutral, typed, immutable, and reference-only. AIGP
OSS owns their schemas, canonical identity rules, and deterministic resolution
semantics. Runtime adapters own framework interception, private-evidence
materialisation, and reports of native execution.

Task 2 adds an in-process, deterministic resolver for these contracts. It does
not intercept tools, materialise evidence, enforce replay results in a worker,
run a framework graph, or provide a sandbox.

The existing `RuntimeReplaySource/v1`, `ReplayInterventionEnvelope`,
`evidence-only-replay-capability/v1`, and
`evidence-only-replay-safety/v1` contracts are unchanged. The Phase 2 types
are optional on `ReplayExecutionContext` and `ReplayExecutionResult`, so
generic and pre-existing runtime adapters remain compatible.

## Capability and Plan

`execution-replay-capability/v1` declares the tool boundaries an
adapter can observe, its unsupported execution surfaces, identity and digest
versions, async/subgraph/retry/concurrency support, and bounded trace limit.
It always requires evidence-only operation and no original-tool fallback.

The declaration does not claim that arbitrary application code is intercepted
or sandboxed. A custom node that performs direct HTTP, database, SDK, or
subprocess I/O is outside the contract unless an adapter explicitly captures
it as a declared boundary.

`evidence-resolution-plan/v1` freezes historical `ReplayToolCall` evidence
before replay. It binds the tenant/project/source execution, manifest hash,
capability, planned call graph, and allowed evidence references to a canonical
plan digest. The plan is immutable: an adapter may consume it, but must not
reconstruct, append, or alter it while replaying.

## Canonical Tool Identity

A `ReplayToolCall` contains only bounded control metadata:

- opaque call ID and graph/subgraph scope ID;
- canonical tool symbol plus schema or alias version;
- canonical argument digest and digest algorithm/key version;
- occurrence within scope, dependencies, and optional retry relationship; and
- for historical calls only, an evidence reference and response digest.

Matching identity excludes wall-clock order. Independent calls may therefore
be scheduled differently, while repeated calls remain distinguishable through
scope, occurrence, dependencies, and retry linkage.

Canonical JSON follows the existing Runtime Action Authorization rule: mapping
keys are sorted, separators are compact, and NaN is rejected. The Plugin API
implements that rule independently so plugins do not depend on Runtime Action
Authorization services or semantics.

The API supports both `sha256-json/v1` and `hmac-sha256-json/v1`. Use the
unkeyed form only when arguments are not sensitive and a fingerprint cannot
enable useful guessing. New persisted fingerprints containing potentially
sensitive, low-entropy values should use the HMAC form. The adapter supplies a
tenant/project-scoped key through `ToolArgumentDigestKeyProvider`; only its
non-secret key version is serialised. Missing or invalid key material is a
failure, never a fallback to another digest.

## Evidence and Private-data Boundary

Control-plane contracts may contain opaque evidence references, digests,
bounded identifiers, counts, and safe reason codes. They must never carry raw
tool arguments, tool responses, prompts, credentials, checkpoint content, or
arbitrary application payloads.

Private evidence remains in the runtime-owned store. Future adapter code will
receive a selected reference from the resolver and materialise its value only
inside that private boundary. Missing, corrupt, or mismatched private evidence
is expected to terminate a replay in a later enforcement increment.

## Trace and Attestation

`ReplayExecutionTrace` records bounded attempted calls, their typed resolution
outcomes, logical dependencies, tool-free branch observations, completion, and
an optional reference/digest for a runtime-private full trace.

`ReplayExecutionAttestation` binds the manifest, frozen plan, intervention,
Phase 1 safety metadata digest, trace digest, declared/exercised tool
boundaries, coverage, and divergence counts. It is an adapter assertion for
future worker validation. It is not independent proof that a runtime avoided
all external side effects.

Tool-call completeness means every intercepted call has a resolution. It is
different from execution-path coverage, which says whether the adapter
observed all of its declared boundaries and whether unsupported surfaces were
encountered.

## Resolution Engine

`ExecutionReplayResolver` consumes one immutable plan in one lock-protected
session. It returns an approved evidence reference and digest only for a full
identity match. It never reads that evidence or invokes the original tool.

Matching uses scope, tool symbol, tool schema or alias version, digest
algorithm and canonicalization version, keyed-digest key version where
applicable, digest, occurrence, retry relationship, and dependencies. The
attempted call ID is only an audit identity; it cannot weaken another mismatch.
Independent dependency-free calls may resolve in either order. A dependent call
must wait until every planned predecessor has been consumed.

The resolver uses this deterministic failure precedence: terminal session,
invalid attempt or digest contract, unknown tool, scope/schema mismatch,
argument mismatch, occurrence/retry mismatch, dependency violation, duplicate
consumption, then intervention binding. The first invalid or blocking
divergence terminates that resolver session.

`ReplayInterventionBinding/v1` is the narrow additive link missing from the
Phase 1 intervention envelope: it binds a pre-authorised replacement evidence
reference to a manifest, plan digest, and planned target call. It deliberately
does not duplicate policy identity or transform evidence. A target call needs
the matching frozen intervention digest, and can consume replacement evidence
only once.

Finalization reports `COMPLETE`, `INCOMPLETE`, or `FAILED` for the plan's
reported governed tool calls. An empty plan completes successfully when no
intervention is required; this is a tool-free-plan policy, not an assertion
that the runtime performed no other activity.

## Deferred Enforcement

Framework interception, LangGraph integration, worker-side attestation
enforcement, Causal Audit changes, sandboxing, and recovery of external effects
remain deferred. Those steps must use these contracts and the resolver without
changing their historical meaning or weakening legacy Replay compatibility.
