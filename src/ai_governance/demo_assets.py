"""Public, versioned canonical identities for the local impact demo.

This is a data contract, not a seed implementation.  Consumers may project
these assets, but Core registry seeding remains their sole creator.
"""

from __future__ import annotations

from dataclasses import dataclass

DEMO_ASSET_MANIFEST_VERSION = "ai-governance.demo-assets/v1"
IMPACT_DEMO_SCENARIOS = (
    "claims-triage",
    "support-assist",
    "fraud-review",
    "knowledge-search",
    "safety-review",
)


@dataclass(frozen=True)
class ImpactDemoAssets:
    slug: str
    model_provider: str
    model_id: str
    model_baseline_version_id: str
    model_baseline_version: str
    model_version_id: str
    model_version: str
    prompt_id: str
    prompt_baseline_version_id: str
    prompt_baseline_version: str
    prompt_version_id: str
    prompt_version: str
    dataset_id: str
    dataset_version_id: str
    dataset_version: str
    policy_id: str
    policy_version: str


def impact_demo_assets(slug: str) -> ImpactDemoAssets:
    """Return the canonical registry identities for one named demo scenario."""
    prefix = f"impact-{slug}"
    return ImpactDemoAssets(
        slug=slug,
        # This manifest describes a governed managed-model reference, so it
        # must use the same canonical runtime-provider vocabulary enforced by
        # ModelRegistryService.  ``mock`` is an evaluation test provider, not
        # a permitted managed-model runtime provider.
        model_provider="openai",
        model_id=f"{prefix}-model",
        model_baseline_version_id=f"{prefix}-model-v1",
        model_baseline_version="v1",
        model_version_id=f"{prefix}-model-v2",
        model_version="v2",
        prompt_id=f"{prefix}-prompt",
        prompt_baseline_version_id=f"{prefix}-prompt-v1",
        prompt_baseline_version="v1",
        prompt_version_id=f"{prefix}-prompt-v2",
        prompt_version="v2",
        dataset_id=f"{prefix}-dataset",
        dataset_version_id=f"{prefix}-dataset-v1",
        dataset_version="v1",
        policy_id=f"{prefix}-policy-v1",
        # PolicyAdministrationService owns numeric versions.  The stable
        # policy *identity* retains the ``-v1`` suffix, while its persisted
        # first version is "1" rather than a second, incompatible spelling.
        policy_version="1",
    )
