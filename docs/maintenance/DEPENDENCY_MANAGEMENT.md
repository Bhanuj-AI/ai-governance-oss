# Dependency Management

This document records durable dependency compatibility and migration decisions.
It is not a replacement for `pyproject.toml`, `uv.lock`, Docker Compose, or the
issue tracker:

- `pyproject.toml` and `uv.lock` are the source of truth for Python packages.
- Compose files are the source of truth for local service-image pins.
- GitHub Issues and Projects are the live backlog for upgrade work, ownership,
  and scheduling.
- This document explains cross-component constraints that are easy to miss when
  reviewing an individual dependency update.

## Upgrade Workflow

1. Dependabot opens a focused dependency PR.
2. Classify the change as a patch/minor package update, an application-library
   major update, or an infrastructure/database migration.
3. Run the relevant automated tests and review upstream release or migration
   notes when the change is major or crosses a component boundary.
4. Create or update a GitHub issue for work that cannot safely be completed in
   the dependency PR, such as a database-server migration.
5. Update this document only when the result establishes a durable
   compatibility, migration, or operational-support decision. Record shipped
   behavior in `CHANGELOG.md`.

Do not update a Docker service image merely because a client library has a
matching version number. Library and service versions are separate release
trains unless their vendor documents a coupled requirement.

## Compatibility Decisions

| Component | Source of truth | Decision |
| --- | --- | --- |
| Neo4j Python driver | `pyproject.toml` and `uv.lock` | The application uses Neo4j Python driver 6.2.x. It can be upgraded independently after focused tests and compatibility review. |
| Local Neo4j server | `docker-compose.yml` | Local development pins Neo4j Community Edition `5.26.27`. The image is changed only through a dedicated server-migration change. |
| Neo4j driver/server relationship | This document and the [Neo4j Operations Guide](../ontology/neo4j-operations-guide.md) | Driver 6.2 supports the Bolt protocol used by Neo4j 5.x. The driver upgrade does not require a matching server-image version; review the vendor compatibility matrix before either side changes. |

## Infrastructure and Database Migrations

Any major database or infrastructure-image upgrade must have a dedicated GitHub
issue and PR. Before changing the image pin:

- review the vendor migration guide and release notes;
- back up and rehearse restoration of representative data;
- test the upgrade against a disposable copy of the persisted volume or
  production-equivalent environment;
- run the opt-in integration suite against the upgraded service;
- update affected operations documentation and `CHANGELOG.md`.

For Neo4j specifically, a server upgrade is distinct from upgrading the Python
driver. The graph projection is rebuildable from authoritative control-plane
records, but it still contains useful operational state and must be handled as
a data migration rather than a routine dependency bump.

## Related Documents

- [Neo4j Operations Guide](../ontology/neo4j-operations-guide.md)
- [Configuration Reference](../reference/CONFIGURATION.md)
- [Roadmap](../roadmap/ROADMAP.md)
