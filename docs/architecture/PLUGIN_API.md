# BHANUJ Governance Plugin API

`bhanuj-governance-plugin-api` is the independently publishable extension
contract for external BHANUJ runtime plugins. It is not the BHANUJ application
SDK and does not include a control plane, persistence, workers, RBAC, settings,
evaluation, ontology, or provider SDKs.

## Dependency direction

```text
ai-governance (host / worker) ──────> bhanuj-governance-plugin-api
external runtime plugin ────────────> bhanuj-governance-plugin-api
```

The Plugin API never imports `ai_governance`. An external runtime must not
import Core models, services, repositories, or worker code merely to implement
the public replay plugin contract.

## v1 scope

Plugin API v1 extracts the existing runtime-plugin contracts:

- `PluginMetadata`, lifecycle typing, and `SPI_VERSION`;
- `ReplayExecutionAdapterContribution` with its versioned adapter identity;
- `ReplayExecutionContext` and cooperative cancellation;
- `ReplayInterventionEnvelope`, the fixed reference-only controlled-replay
  wire contract; and
- `ReplayExecutionResult`, which Core materialises as its own canonical
  workflow execution record.

The envelope contains only policy and intervention provenance. It never
contains raw tool evidence, prompts, responses, tool arguments/results, or
reasoning. The external runtime resolves `counterfactual_reference` inside its
own boundary and fails closed if that value cannot be resolved or its digest
does not match.

Core's broader in-process provider, hook, event, route, and persistence
extension surfaces remain Core-hosted compatibility APIs. They are not copied
into the Plugin API until they can be represented without importing Core
models. This keeps the package small and avoids treating it as a generic SDK.

## Versioning and registration

The package starts at `1.0.0` and uses normal semantic versioning. `SPI_VERSION`
is currently `"1"`; plugins declare the supported major through
`PluginMetadata(spi_version="1")`. A host rejects an unsupported major before
plugin validation or registration.

New packages register in the canonical entry-point group:

```toml
[project]
dependencies = ["bhanuj-governance-plugin-api>=1.0,<2"]

[project.entry-points."bhanuj.governance.plugins"]
my-runtime = "my_runtime.plugin:MyRuntimePlugin"
```

Core temporarily reads the legacy `ai_governance.plugins` group into the same
registry for compatibility. It is not a second plugin system; new plugins must
use `bhanuj.governance.plugins`.

## Minimal external runtime plugin

```python
from bhanuj_governance_plugin_api import (
    PluginMetadata,
    ReplayExecutionAdapterContribution,
)


class MyRuntimePlugin:
    metadata = PluginMetadata(
        name="my-runtime",
        version="1.0.0",
        required_ai_governance_version=">=1.1,<2",
        capabilities=("replay.execute",),
        spi_version="1",
    )

    def validate(self, context):
        pass

    def register(self, context):
        context.contributions.replay_execution_adapters((
            ReplayExecutionAdapterContribution("my-runtime", "v1", MyAdapter()),
        ))

    def start(self, context):
        pass

    def stop(self, context):
        pass
```

`MyAdapter` returns `ReplayExecutionResult`; Core owns the canonical workflow
record, its identity, tenant scope, snapshots, persistence, and lineage.

## Local development

External packages may use a temporary `tool.uv.sources` path to this package
while its wheel is unpublished. That override must point to
`bhanuj-governance-plugin-api`, never to the `ai-governance` Core checkout. A
published plugin declares only the bounded package dependency above.

## Release verification

Build each distributable without development source overrides, then install
the Plugin API wheel before the host or external runtime wheel in a clean
environment:

```sh
# From the OSS repository root
uv build --no-sources --wheel --out-dir dist/core
uv build --directory packages/bhanuj-governance-plugin-api \
  --no-sources --wheel --out-dir ../../dist/plugin-api

# From an external runtime repository
uv build --no-sources --wheel --out-dir dist

python -m venv /tmp/bhanuj-plugin-test
source /tmp/bhanuj-plugin-test/bin/activate
pip install /path/to/bhanuj_governance_plugin_api-*.whl
pip install /path/to/reference_openai_agent_runtime-*.whl
pip check
```

`--no-sources` proves that `[tool.uv.sources]` is not part of the release
dependency graph. The project dependency declarations and wheel metadata are
the only dependency inputs in this verification.
