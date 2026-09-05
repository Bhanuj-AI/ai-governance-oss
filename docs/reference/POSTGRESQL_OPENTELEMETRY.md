# PostgreSQL OpenTelemetry Instrumentation

This guide defines how an AI Governance Control Plane deployment should
instrument **client calls to PostgreSQL** with OpenTelemetry. It applies to the
PostgreSQL repository implementation and any integration that issues database
commands on the control plane's behalf.

It does not change the product's optional, aggregate usage telemetry described
in [Telemetry](./TELEMETRY.md). OpenTelemetry traces and metrics are operational
observability signals owned and configured by the deployment; product telemetry
is a separate, privacy-preserving feature.

The conventions in this guide are based on OpenTelemetry's
[PostgreSQL client semantic conventions](https://opentelemetry.io/docs/specs/semconv/db/postgresql/).
Use the linked specification as the authority if its stable conventions evolve.

## Scope and boundary

Instrument a database **client operation**, not a service use case. For
example, `create causal audit` may have an application span, while each query
or transaction it issues is represented by one or more nested PostgreSQL
`CLIENT` spans.

```text
HTTP request / worker job
  └── application-service span
        └── PostgreSQL CLIENT span
              └── database operation
```

Repository adapters remain responsible for data access. Instrumentation must
not cause a service to select a database backend, bypass tenant-context
enforcement, or add database-specific logic above the repository layer.

## Required Span Identity

Every PostgreSQL client span must set:

| Field | Value | Notes |
| --- | --- | --- |
| Span kind | `CLIENT` | Represents an outbound call from the control plane to PostgreSQL. |
| `db.system.name` | `postgresql` | Required by the PostgreSQL semantic convention; set it when the span is created. |
| Span status | success or error | Record an error status for failed operations using the OpenTelemetry error-recording guidance. |

Use a low-cardinality name. Prefer `db.query.summary`; otherwise use an
operation and stable target such as `INSERT agent_execution` or
`SELECT causal_audit`.

## Recommended Attributes

Set an attribute only when it is available without an extra database call and
when it can be safely emitted. The following attributes are the normal set for
the PostgreSQL repository adapters.

| Attribute | When to set it | Safe example |
| --- | --- | --- |
| `db.namespace` | Database and schema are known from the connection or configuration. | `governance|public` |
| `db.operation.name` | A single operation name is readily available. Do not parse it from arbitrary SQL text. | `SELECT`, `INSERT`, `UPDATE` |
| `db.query.summary` | A low-cardinality query class is available or can be generated safely. | `SELECT causal_audit`, `INSERT replay` |
| `db.collection.name` | The operation clearly targets one table. | `causal_audit` |
| `server.address` | Host name or address is safe to expose to the configured observability backend. | `postgres.internal` |
| `server.port` | Port is known. | `5432` |
| `db.response.status_code` | PostgreSQL returned a SQLSTATE or comparable response code. | `23505` |
| `error.type` | The operation failed. | `timeout`, `psycopg.OperationalError` |

For PostgreSQL, `db.namespace` combines database and schema as
`{database}|{schema}` when both are available. If the current schema cannot be
observed without issuing an additional query, use the schema from connection
setup and document that choice in the instrumentation configuration.

For a real batch of two or more independently submitted operations, set
`db.operation.batch.size`. A single SQL command that affects multiple rows is
not a batch solely for that reason.

## Query Text and Privacy

`db.query.summary` is the preferred grouping key. It gives operators useful
query-level visibility without creating high-cardinality traces or exporting
database values.

Do not emit raw SQL literals, query parameter values, tenant or project IDs,
actor identifiers, evidence references, prompts, responses, credentials, or
secrets as span attributes. In particular:

- Do not enable `db.query.parameter.<key>` in production control-plane
  instrumentation.
- Emit `db.query.text` only when the query is parameterized and the deployment
  has reviewed the statement for sensitive data. Non-parameterized query text
  must be sanitized before it is recorded.
- Prefer an allow-listed summary over query text for statements that touch
  tenant-scoped governance evidence.

Good:

```text
db.operation.name = "SELECT"
db.collection.name = "causal_audit"
db.query.summary = "SELECT causal_audit by tenant and execution"
```

Not acceptable:

```text
db.query.text = "SELECT * FROM causal_audit WHERE organization_id = 'acme'"
db.query.parameter.organization_id = "acme"
```

## Example span

The following is a representative, safe span for a persisted Causal Audit
lookup. Values are illustrative.

```json
{
  "name": "SELECT causal_audit",
  "kind": "CLIENT",
  "attributes": {
    "db.system.name": "postgresql",
    "db.namespace": "ai_governance|public",
    "db.operation.name": "SELECT",
    "db.collection.name": "causal_audit",
    "db.query.summary": "SELECT causal_audit by scoped identifier",
    "server.address": "postgres.internal",
    "server.port": 5432
  }
}
```

For a failed operation, preserve the same stable attributes and add the
database response code when available. The exception message and SQL values
must not be copied into telemetry attributes.

```json
{
  "status": "ERROR",
  "attributes": {
    "db.system.name": "postgresql",
    "db.operation.name": "INSERT",
    "db.collection.name": "causal_audit",
    "db.response.status_code": "23505",
    "error.type": "unique_constraint_violation"
  }
}
```

## Metrics

PostgreSQL client instrumentation should use the OpenTelemetry database-client
metric conventions. Preserve the same low-cardinality database-system,
namespace, operation, and collection dimensions where appropriate. Do not add
tenant, project, execution, audit, replay, policy, or tool-call identifiers as
metric dimensions: they create unbounded cardinality and can expose governance
scope.

Operational dashboards should answer questions such as:

- Which PostgreSQL operation classes are slow or failing?
- Are replay and causal-audit persistence operations timing out?
- Has a migration or deployment changed database error rates?

They should not be used to reconstruct a tenant's runtime evidence or to
measure product usage. Use governed records and access-controlled product
views for that purpose.

## Implementation Checklist

- Create PostgreSQL spans in the concrete repository/driver instrumentation,
  nested below the invoking request or worker span.
- Set `db.system.name=postgresql` and `CLIENT` kind at span creation.
- Prefer safe `db.query.summary` and `db.collection.name` over query text.
- Record failures with OpenTelemetry error status, `error.type`, and a safe
  SQLSTATE in `db.response.status_code` when available.
- Keep tenant context in normal application and repository contracts; never
  use telemetry attributes as an authorization mechanism.
- Test that the exporter receives no raw parameters, evidence payloads,
  credentials, or tenant-identifying values.
- Treat database-convention upgrades as an observability compatibility change:
  document the emitted convention version and use the OpenTelemetry migration
  guidance before changing existing stable attributes.

## References

- [OpenTelemetry: Semantic conventions for PostgreSQL client operations](https://opentelemetry.io/docs/specs/semconv/db/postgresql/)
- [OpenTelemetry: Semantic conventions for database client spans](https://opentelemetry.io/docs/specs/semconv/db/database-spans/)
- [OpenTelemetry: Semantic conventions for database client metrics](https://opentelemetry.io/docs/specs/semconv/db/database-metrics/)
