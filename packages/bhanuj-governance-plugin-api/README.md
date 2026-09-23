# BHANUJ Governance Plugin API

`bhanuj-governance-plugin-api` is the small, versioned extension contract for
external BHANUJ runtime plugins. It is not the BHANUJ application SDK: it does
not contain a control plane, persistence, workers, settings, RBAC, or provider
implementations.

## Install

```toml
[project]
dependencies = ["bhanuj-governance-plugin-api>=1.0,<2"]

[project.entry-points."bhanuj.governance.plugins"]
my-runtime = "my_runtime.plugin:MyRuntimePlugin"
```

## Boundary

The package supplies lifecycle metadata, the replay-adapter contribution,
bounded replay context, and the governed intervention envelope. The host owns
replay persistence, the canonical workflow execution record, and policy
evaluation. Plugins return `ReplayExecutionResult`; the host materialises its
own execution record.

The package has no dependency on `ai-governance` and must never import Core.
`SPI_VERSION` is currently `"1"`. Plugins declare the major version they
implement with `PluginMetadata(spi_version="1")`; an unsupported major fails
host startup explicitly.
