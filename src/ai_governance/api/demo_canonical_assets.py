"""Idempotent Core-owned persistence for the public impact-demo manifest."""

from __future__ import annotations

from ai_governance.decisions import (
    DecisionTargetType,
    PolicyCondition,
    PolicyEffect,
    PolicyRule,
)
from ai_governance.demo_assets import (
    DEMO_ASSET_MANIFEST_VERSION,
    IMPACT_DEMO_SCENARIOS,
    impact_demo_assets,
)
from ai_governance.services.datasets.dataset_registry_service import (
    DatasetNotFoundError,
)
from ai_governance.services.models.model_registry_service import ModelNotFoundError
from ai_governance.services.policies.policy_administration_service import (
    PolicyAdminNotFoundError,
)
from ai_governance.services.prompts.prompt_registry_service import PromptNotFoundError
from ai_governance.tenancy.domain import TenantContext


def seed_canonical_impact_demo_assets(
    *, models, prompts, datasets, policies, context: TenantContext
) -> tuple[str, ...]:
    """Create manifest identities through the normal registry/admin services."""
    if not context.project_id:
        raise ValueError("canonical impact demo assets require a project-scoped tenant")

    created: list[str] = []
    for slug in IMPACT_DEMO_SCENARIOS:
        asset = impact_demo_assets(slug)
        for version_id, version, activate in (
            (
                asset.model_baseline_version_id,
                asset.model_baseline_version,
                False,
            ),
            (asset.model_version_id, asset.model_version, True),
        ):
            try:
                model = models.get_model(version_id, context)
            except ModelNotFoundError:
                model = models.register_model(
                    asset.model_provider,
                    asset.model_id,
                    version,
                    {"temperature": 0.0},
                    8192,
                    "demo-seed",
                    context,
                    provider_model_id=asset.model_id,
                    model_id=version_id,
                )
                created.append(version_id)
            if activate and str(model.status).upper().endswith("DRAFT"):
                models.activate_model_version(model.model_id, context)
        for version_id, version, template, activate in (
            (
                asset.prompt_baseline_version_id,
                asset.prompt_baseline_version,
                "Use supplied evidence.",
                False,
            ),
            (
                asset.prompt_version_id,
                asset.prompt_version,
                "Use supplied evidence and cite the governing policy.",
                True,
            ),
        ):
            try:
                prompt = prompts.get_prompt(version_id, context)
            except PromptNotFoundError:
                prompt = prompts.create_prompt(
                    asset.prompt_id,
                    version,
                    template,
                    (),
                    "demo-seed",
                    context,
                    prompt_id=version_id,
                )
                created.append(version_id)
            if activate and str(prompt.status).upper().endswith("DRAFT"):
                prompts.activate_prompt(prompt.prompt_id, context)
        try:
            datasets.get_dataset(asset.dataset_version_id, context)
        except DatasetNotFoundError:
            dataset = datasets.register_dataset(
                asset.dataset_id,
                asset.dataset_version,
                "Canonical impact demo dataset.",
                f"memory://impact-demo/{slug}",
                "memory",
                "v1",
                1,
                f"sha256:impact-{slug}-dataset-v1",
                "demo-seed",
                context.organization_id,
                context.project_id,
                dataset_id=asset.dataset_version_id,
            )
            datasets.freeze_dataset(dataset.dataset_id, context)
            created.append(asset.dataset_version_id)
        try:
            policies.get_policy_version(asset.policy_id, asset.policy_version)
        except PolicyAdminNotFoundError:
            policies.create_policy(
                policy_id=asset.policy_id,
                name=f"Impact {slug}",
                description="Canonical impact demo policy.",
                organization_id=context.organization_id,
                project_id=context.project_id,
                category="MODEL_RISK",
                owner="demo-seed",
                created_by="demo-seed",
                target_types=(DecisionTargetType.MODEL_VERSION,),
                rules=(
                    PolicyRule(
                        f"{asset.policy_id}-rule",
                        "Require evidence",
                        (
                            PolicyCondition(
                                "model.provider",
                                "EQUALS",
                                asset.model_provider,
                            ),
                        ),
                        PolicyEffect.APPROVE,
                        "Demo evidence accepted.",
                        1,
                    ),
                ),
                metadata={"manifest_version": DEMO_ASSET_MANIFEST_VERSION},
            )
            policies.activate_version(
                policy_id=asset.policy_id,
                version=asset.policy_version,
                activated_by="demo-seed",
            )
            created.append(asset.policy_id)
    return tuple(created)
