# Telemetry

AI Governance Control Plane telemetry is an optional, privacy-preserving way to
understand anonymous OSS adoption and aggregate workload characteristics. It is
not billing, user analytics, clickstream tracking, OpenTelemetry export, or a
replacement for operational observability.

## Defaults and disabling telemetry

`telemetry.mode` defaults to `standard`. Essential telemetry is enabled by
default; product analytics and performance research are disabled by default.
The bundled exporter defaults to `none`, so a new installation makes no
outbound request until an operator selects and configures an exporter.

Set `AI_GOVERNANCE_TELEMETRY_MODE=disabled` (or update `telemetry.mode` in
Settings) for air-gapped deployments. Disabled mode sends zero outbound
telemetry, clears pending snapshots, and does not require any PostHog
configuration.

The system-scoped settings are:

- `telemetry.mode`: `standard` or `disabled`
- `telemetry.essential.enabled`
- `telemetry.product_analytics.enabled`
- `telemetry.performance_research.enabled`
- `telemetry.exporter.type`: `none` or `posthog`
- `telemetry.exporter.posthog_api_key_ref`: secret reference such as
  `env://POSTHOG_API_KEY`
- `telemetry.exporter.posthog_endpoint`: HTTPS capture endpoint
- `telemetry.aggregation_period`: defaults to `1d`

PostHog keys are resolved through the existing `env://` secret-reference
mechanism. Never put a plaintext key in a runtime setting.

## Exactly what can be transmitted

Snapshots are aggregated locally by period and use schema version `1`.
Every payload has only these top-level fields:

```json
{
  "schema_version": "1",
  "installation_id": "UUID generated locally",
  "ai_governance_version": "release version",
  "period_start": "RFC 3339 timestamp",
  "period_end": "RFC 3339 timestamp",
  "category": "ESSENTIAL | PRODUCT_ANALYTICS | PERFORMANCE_RESEARCH",
  "metrics": { "named_counter": 0 },
  "distributions": { "named_duration": { "fixed_bucket": 0 } }
}
```

`ESSENTIAL` may contain `installation_started` and
`installation_upgraded`. `PRODUCT_ANALYTICS` may contain only:
`governed_executions`, `evaluation_runs`, `replay_runs`,
`governance_decisions`, `impact_simulations`, `behavior_contracts_created`,
`prompt_assets`, `model_assets`, `dataset_assets`,
`evaluation_provider_assets`, and `job_executions`.

`PERFORMANCE_RESEARCH` may contain fixed-bucket aggregate distributions for
`job_execution_duration`, `evaluation_duration`, `replay_duration`, and
`impact_simulation_duration`. The buckets are 10ms, 100ms, 1s, 10s, 60s, and
greater than 60s, plus count/min/max.

The generated installation ID is a random UUID stored locally in the selected
settings persistence. It is unrelated to tenant, organization, user, host,
IP, MAC address, or customer identity. Deleting telemetry state regenerates
the ID.

Payloads are allow-listed and validated immediately before delivery. They can
never contain prompts, responses, datasets, evidence, policies, ontology
content, behavior-contract content, model inputs or outputs, names, emails,
tenant/project/organization IDs or names, customer labels, secrets, API keys,
tokens, paths, URLs, stack traces, or arbitrary metadata.

## PostHog

The PostHog adapter is isolated behind the public `TelemetryExporter` SPI and
uses direct HTTPS ingestion. It emits only `ai_governance_installation`,
`ai_governance_usage_daily`, or `ai_governance_performance_daily`; the anonymous
installation UUID is the PostHog `distinct_id`.

Configure `telemetry.exporter.type=posthog` and an `env://` API-key reference.
The endpoint must be HTTPS and uses a short bounded timeout. The application
does not log telemetry payloads or credentials.

## Visibility and reliability

Operators with Settings read permission can inspect:

- `GET /api/v1/telemetry/status`
- `GET /api/v1/telemetry/preview`

Preview is read-only: it returns the exact sanitized payloads without enqueueing
or transmitting anything. A low-priority delivery thread exports only already
aggregated snapshots. Pending snapshots are bounded to 30, retries are bounded
to three attempts, and exporter failures are isolated from runtime workflows.
Internal telemetry health counters are available through the status response.

Any new field requires a telemetry schema-version change, privacy review, and
documentation update.
