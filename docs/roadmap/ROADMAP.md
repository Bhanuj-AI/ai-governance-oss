# Roadmap

This roadmap reflects the current direction of the repository. It is a planning
artifact, not a release commitment.

## Direction at a glance

- ✅ **OSS Foundation** — governed assets, deterministic policy decisions,
  evidence, lineage, audit, replay, Studio, REST APIs, and MCP tools.
- 🚧 **Identity Provider Integrations** — extend production authentication and
  identity-provider support while preserving the existing tenant and
  authorization contracts.
- 🚧 **Connector Framework** — make it easier to bring governance evidence in
  from AI runtimes, data systems, and operational tools.
- 🚧 **Compliance Packs** — reusable, versioned governance policy and evidence
  packs for common compliance workflows.
- 🔬 **Future Research** — new evaluation approaches, governance insights, and
  operational intelligence.

This is direction, not a release commitment. The detailed list below records
what is already available and the areas under consideration.

## Implemented

- Governance Ontology Design
- Ontology Foundation
- Ontology Synchronization
- Execution Audit
- Workflow Replay
- Evaluation Framework
- Evaluation Worker
- Job Execution Control Plane
- Job Submission Service
- Job Worker
- Job Repository
- TruLens Provider
- Evaluation Persistence
- SQLite Repository
- PostgreSQL Repository
- Snowflake Repository
- Evaluation History
- Evaluation Comparison
- Drift Analysis
- Replay-aware Governance
- Governance API
- Leaderboard API
- REST Control Plane
- REST Registry APIs
- REST Evaluation APIs
- REST Experiment APIs
- REST Governance APIs
- REST Job APIs
- MCP Server Read Tools
- MCP Server Controlled Writes
- Prompt Registry
- Prompt Versioning
- Prompt Lifecycle Management
- Prompt Diffing
- Model Registry
- Model Versioning
- Model Lifecycle Management
- Model Version Comparison
- Dataset Registry
- Dataset Versioning
- Dataset Lifecycle Management
- Dataset Version Comparison
- S3-compatible dataset content storage for local SeaweedFS and production S3
- Registry-centric Assets workspace for prompts, models, datasets, and
  evaluation providers
- Asset version references, bounded ontology lineage, and audit history
- Experiment Lifecycle Management
- Experiment Orchestration
- Experiment Candidates
- Candidate Configuration Comparison
- Experiment Evaluation Runs
- Winner Selection
- Experiment Ranking
- Leaderboards

## Near-Term

- Additional evaluation providers

## Future

- Advanced multi-organization governance and administration
- Dataset Statistical Drift
- Operational intelligence dashboards beyond the OSS registry scope

## Notes

The roadmap may evolve as platform boundaries and operational needs become
clearer. Items should be read as direction rather than promise.

## Related Documents

- [Vision](./VISION.md)
- [Architecture](../architecture/ARCHITECTURE.md)
- [Governance Ontology](../architecture/GOVERNANCE_ONTOLOGY.md)
- [Ontology Foundation](../ontology/ontology-foundation.md)
- [Ontology Synchronization](../ontology/ontology-synchronization.md)
- [Extensibility](../architecture/EXTENSIBILITY.md)
