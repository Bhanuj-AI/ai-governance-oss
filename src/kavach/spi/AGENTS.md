# Scope

This directory owns public extension and provider contracts consumed by Kavach
core and separately released plugins.

## Architectural Facts

`KavachPlugin` implementations may consume `kavach.spi`, `kavach.plugins`,
`kavach.hooks`, and `kavach.events`. Provider selection and explicit replacement
are owned by the plugin registry; see `docs/architecture/EXTENSIBILITY.md`.

## Dependency Boundaries

SPI contracts remain transport- and implementation-neutral. Do not import
concrete plugins, database adapters, FastAPI, services, repositories, or
application-composition modules into this package. This keeps an independently
released extension compatible with OSS without depending on runtime internals.

## Change Rules

- Prefer additive optional members. A breaking SPI change requires an explicit
  compatibility and migration plan.
- Specify tenant context, failure, timeout, cancellation, and idempotency
  behavior when the contract crosses one of those boundaries.
- Keep provider-specific behavior outside the SPI. Contract tests must be
  reusable by every provider implementation.

## Validation

Use the relevant provider contract coverage under `tests/providers/contracts`
and the extension tests in `tests/unit/test_extension_framework.py` and
`tests/unit/test_plugin_contributions.py`.
