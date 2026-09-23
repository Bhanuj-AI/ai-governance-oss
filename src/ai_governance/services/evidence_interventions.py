"""Deterministic structured-JSON intervention provider and orchestration helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from ai_governance.domain.causal_audit import (
    CounterfactualEvidence,
    EvidenceInterventionPolicy,
    ToolEvidenceDescriptor,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.spi.evidence_intervention import (
    EvidenceInterventionProvider,
    EvidenceValueResolver,
)
from ai_governance.tenancy.domain import TenantContext


class InterventionError(ValueError):
    code = "COUNTERFACTUAL_GENERATION_FAILED"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or type(self).code


class UnsupportedEvidenceType(InterventionError):
    code = "UNSUPPORTED_EVIDENCE_TYPE"


class EvidenceSchemaUnavailable(InterventionError):
    code = "EVIDENCE_SCHEMA_UNAVAILABLE"


class EvidenceResolutionFailed(InterventionError):
    code = "EVIDENCE_RESOLUTION_FAILED"


class CounterfactualValidationFailed(InterventionError):
    code = "COUNTERFACTUAL_VALIDATION_FAILED"


class NoEffectiveIntervention(InterventionError):
    code = "NO_EFFECTIVE_INTERVENTION"


class EvidenceInterventionProviderRegistry:
    def __init__(
        self, providers: tuple[EvidenceInterventionProvider, ...] = ()
    ) -> None:
        self._providers = {
            (item.provider_id, item.provider_version): item for item in providers
        }

    def resolve(
        self, policy: EvidenceInterventionPolicy
    ) -> EvidenceInterventionProvider:
        provider = self._providers.get((policy.provider_id, policy.provider_version))
        if provider is None:
            raise InterventionError(
                f"INTERVENTION_PROVIDER_NOT_AVAILABLE: {policy.provider_id}/{policy.provider_version}",
                code="INTERVENTION_PROVIDER_NOT_AVAILABLE",
            )
        return provider


class StructuredJsonEvidenceInterventionProvider:
    """Small, declarative-only provider for JSON-compatible evidence."""

    provider_id = "structured-json"
    provider_version = "v1"

    def __init__(self, resolver: EvidenceValueResolver) -> None:
        self._resolver = resolver

    def supports(
        self, descriptor: ToolEvidenceDescriptor, strategy: ControlledEvidenceStrategy
    ) -> bool:
        return descriptor.content_type == "application/json" and strategy in set(
            ControlledEvidenceStrategy
        )

    def validate_policy(
        self, policy: EvidenceInterventionPolicy, context: TenantContext
    ) -> None:
        configuration = policy.strategy_configuration
        schema = configuration.get("json_schema")
        if not isinstance(schema, Mapping):
            raise EvidenceSchemaUnavailable("EVIDENCE_SCHEMA_UNAVAILABLE")
        try:
            Draft202012Validator.check_schema(dict(schema))
        except SchemaError as error:
            raise EvidenceSchemaUnavailable("EVIDENCE_SCHEMA_UNAVAILABLE") from error
        if (
            ControlledEvidenceStrategy.NULLIFY in policy.allowed_strategies
            and "neutral_value" not in configuration
        ):
            raise CounterfactualValidationFailed(
                "NULLIFY policy requires a schema-valid neutral_value."
            )
        if ControlledEvidenceStrategy.REPLACE in policy.allowed_strategies:
            references = configuration.get("replacement_references")
            if (
                not isinstance(references, list)
                or not references
                or not all(
                    isinstance(item, str) and item.strip() for item in references
                )
            ):
                raise CounterfactualValidationFailed(
                    "REPLACE policy requires replacement_references."
                )
            for reference in references:
                replacement = self._resolver.resolve(reference, context)
                self._validate_schema(replacement, policy)
        if ControlledEvidenceStrategy.PERTURB in policy.allowed_strategies:
            operations = configuration.get("operations")
            if not isinstance(operations, list) or not operations:
                raise CounterfactualValidationFailed(
                    "PERTURB policy requires operations."
                )
            for operation in operations:
                if not isinstance(operation, Mapping) or operation.get(
                    "operation"
                ) not in {"SET", "NUMERIC_DELTA", "NUMERIC_SCALE", "REMOVE_OPTIONAL"}:
                    raise CounterfactualValidationFailed(
                        "PERTURB supports only declared bounded operations."
                    )

    def generate(
        self,
        original_evidence: Any,
        descriptor: ToolEvidenceDescriptor,
        policy: EvidenceInterventionPolicy,
        strategy: ControlledEvidenceStrategy,
        seed: int,
        context: TenantContext,
    ) -> tuple[Any, CounterfactualEvidence]:
        if not self.supports(descriptor, strategy):
            raise UnsupportedEvidenceType("UNSUPPORTED_EVIDENCE_TYPE")
        self.validate_policy(policy, context)
        self._validate_schema(original_evidence, policy)
        if strategy not in policy.allowed_strategies:
            raise CounterfactualValidationFailed("UNSUPPORTED_INTERVENTION")
        if strategy is ControlledEvidenceStrategy.NULLIFY:
            counterfactual = deepcopy(policy.strategy_configuration["neutral_value"])
            selected_reference = f"policy:{policy.policy_id}:neutral:{policy.version}"
        elif strategy is ControlledEvidenceStrategy.REPLACE:
            references = policy.strategy_configuration["replacement_references"]
            selected_reference = references[seed % len(references)]
            counterfactual = self._resolver.resolve(selected_reference, context)
        else:
            counterfactual = deepcopy(original_evidence)
            for operation in policy.strategy_configuration["operations"]:
                _apply_operation(counterfactual, operation)
            selected_reference = (
                f"policy:{policy.policy_id}:perturb:{policy.version}:{seed}"
            )
        self._validate_schema(counterfactual, policy)
        self.validate_semantics(counterfactual, policy, context)
        original_digest = self._resolver.digest(original_evidence)
        counterfactual_digest = self._resolver.digest(counterfactual)
        if original_digest == counterfactual_digest:
            raise NoEffectiveIntervention("NO_EFFECTIVE_INTERVENTION")
        reference = self._resolver.put_counterfactual(
            counterfactual,
            context,
            {
                "policy_id": policy.policy_id,
                "policy_version": policy.version,
                "provider_id": self.provider_id,
                "provider_version": self.provider_version,
                "source_reference": selected_reference,
                "seed": seed,
            },
        )
        return counterfactual, CounterfactualEvidence(
            strategy=strategy,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            seed=seed,
            original_evidence_digest=original_digest,
            counterfactual_evidence_ref=reference,
            counterfactual_evidence_digest=counterfactual_digest,
            schema_valid=True,
            semantic_valid=True,
            generation_metadata={"selected_reference": selected_reference},
        )

    def validate_semantics(
        self,
        counterfactual_evidence: Any,
        policy: EvidenceInterventionPolicy,
        context: TenantContext,
    ) -> None:
        if not isinstance(counterfactual_evidence, (dict, list)):
            raise CounterfactualValidationFailed(
                "Structured JSON evidence must be an object or array."
            )

    @staticmethod
    def _validate_schema(value: Any, policy: EvidenceInterventionPolicy) -> None:
        try:
            Draft202012Validator(
                dict(policy.strategy_configuration["json_schema"])
            ).validate(value)
        except (ValidationError, SchemaError, TypeError) as error:
            raise CounterfactualValidationFailed(
                "COUNTERFACTUAL_VALIDATION_FAILED: evidence does not satisfy its schema."
            ) from error


class OpaqueReferenceEvidenceInterventionProvider:
    """Generate governed counterfactual handles without materialising evidence.

    An external runtime can validate and apply the actual change within its
    isolated replay boundary. Core retains only a policy-authorized opaque
    reference and digest. The target runtime tool-call identity is owned by
    the typed execution event context, never evidence-descriptor metadata.
    """

    provider_id = "opaque-reference"
    provider_version = "v1"

    def supports(
        self, descriptor: ToolEvidenceDescriptor, strategy: ControlledEvidenceStrategy
    ) -> bool:
        return strategy in set(ControlledEvidenceStrategy)

    def validate_policy(
        self, policy: EvidenceInterventionPolicy, context: TenantContext
    ) -> None:
        del context
        static_reference = policy.strategy_configuration.get("counterfactual_reference")
        static_digest = policy.strategy_configuration.get("counterfactual_digest")
        if static_reference is not None or static_digest is not None:
            if (
                policy.allowed_strategies != (ControlledEvidenceStrategy.REPLACE,)
                or not isinstance(static_reference, str)
                or not static_reference.strip()
                or not isinstance(static_digest, str)
                or not static_digest.strip()
            ):
                raise CounterfactualValidationFailed(
                    "Static opaque counterfactuals require only REPLACE plus a reference and digest."
                )
            if (
                policy.strategy_configuration.get("runtime_attests_validation")
                is not True
            ):
                raise CounterfactualValidationFailed(
                    "Reference-only policies require runtime_attests_validation=true."
                )
            return
        namespace = policy.strategy_configuration.get(
            "counterfactual_reference_namespace"
        )
        if not isinstance(namespace, str) or not namespace.strip():
            raise CounterfactualValidationFailed(
                "Reference-only policies require a counterfactual_reference_namespace."
            )
        if policy.strategy_configuration.get("runtime_attests_validation") is not True:
            raise CounterfactualValidationFailed(
                "Reference-only policies require runtime_attests_validation=true."
            )

    def generate_reference_only(
        self,
        descriptor: ToolEvidenceDescriptor,
        policy: EvidenceInterventionPolicy,
        strategy: ControlledEvidenceStrategy,
        seed: int,
        context: TenantContext,
    ) -> CounterfactualEvidence:
        if not self.supports(descriptor, strategy):
            raise UnsupportedEvidenceType("UNSUPPORTED_EVIDENCE_TYPE")
        self.validate_policy(policy, context)
        static_reference = policy.strategy_configuration.get("counterfactual_reference")
        static_digest = policy.strategy_configuration.get("counterfactual_digest")
        if static_reference is not None or static_digest is not None:
            if strategy is not ControlledEvidenceStrategy.REPLACE:
                raise CounterfactualValidationFailed("UNSUPPORTED_INTERVENTION")
            if static_digest == descriptor.evidence_digest:
                raise NoEffectiveIntervention("NO_EFFECTIVE_INTERVENTION")
            return CounterfactualEvidence(
                strategy=strategy,
                provider_id=self.provider_id,
                provider_version=self.provider_version,
                policy_id=policy.policy_id,
                policy_version=policy.version,
                seed=seed,
                original_evidence_digest=descriptor.evidence_digest,
                counterfactual_evidence_ref=static_reference,
                counterfactual_evidence_digest=static_digest,
                schema_valid=True,
                semantic_valid=True,
                generation_metadata={"mode": "runtime-attested-static-reference"},
            )
        digest = (
            "sha256:"
            + sha256(
                "|".join(
                    (
                        descriptor.evidence_digest,
                        policy.policy_digest,
                        strategy.value,
                        str(seed),
                    )
                ).encode()
            ).hexdigest()
        )
        namespace = str(
            policy.strategy_configuration["counterfactual_reference_namespace"]
        ).rstrip(":/")
        return CounterfactualEvidence(
            strategy=strategy,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            seed=seed,
            original_evidence_digest=descriptor.evidence_digest,
            counterfactual_evidence_ref=(
                f"{namespace}:{digest.removeprefix('sha256:')[:20]}"
            ),
            counterfactual_evidence_digest=digest,
            schema_valid=True,
            semantic_valid=True,
            generation_metadata={"mode": "runtime-attested-reference-only"},
        )

    def generate(self, *args, **kwargs):
        raise AssertionError("Reference-only provider must not resolve raw evidence.")

    def validate_semantics(self, *args, **kwargs) -> None:
        return None


def _apply_operation(value: Any, operation: Mapping[str, Any]) -> None:
    path = operation.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        raise CounterfactualValidationFailed(
            "PERTURB operation requires a JSON-pointer path."
        )
    parent, key = _pointer_parent(value, path)
    kind = operation["operation"]
    if kind == "REMOVE_OPTIONAL":
        if not isinstance(parent, dict) or key not in parent:
            raise CounterfactualValidationFailed(
                "REMOVE_OPTIONAL target is unavailable."
            )
        parent.pop(key)
        return
    current = parent.get(key) if isinstance(parent, dict) else parent[int(key)]
    if kind == "SET":
        updated = operation.get("value")
    elif kind == "NUMERIC_DELTA":
        if not isinstance(current, (int, float)) or not isinstance(
            operation.get("delta"), (int, float)
        ):
            raise CounterfactualValidationFailed(
                "NUMERIC_DELTA requires numeric target and delta."
            )
        updated = current + operation["delta"]
    elif kind == "NUMERIC_SCALE":
        if not isinstance(current, (int, float)) or not isinstance(
            operation.get("scale"), (int, float)
        ):
            raise CounterfactualValidationFailed(
                "NUMERIC_SCALE requires numeric target and scale."
            )
        updated = current * operation["scale"]
    else:
        raise CounterfactualValidationFailed("Unsupported perturbation operation.")
    if "minimum" in operation and updated < operation["minimum"]:
        raise CounterfactualValidationFailed(
            "PERTURB result is below configured minimum."
        )
    if "maximum" in operation and updated > operation["maximum"]:
        raise CounterfactualValidationFailed(
            "PERTURB result is above configured maximum."
        )
    if "allowed_values" in operation and updated not in operation["allowed_values"]:
        raise CounterfactualValidationFailed(
            "PERTURB result is outside configured allowed_values."
        )
    if isinstance(parent, dict):
        parent[key] = updated
    else:
        parent[int(key)] = updated


def _pointer_parent(value: Any, path: str) -> tuple[Any, str]:
    tokens = [
        item.replace("~1", "/").replace("~0", "~") for item in path.split("/")[1:]
    ]
    if not tokens:
        raise CounterfactualValidationFailed("Root replacement is not supported.")
    parent = value
    for token in tokens[:-1]:
        try:
            parent = parent[token] if isinstance(parent, dict) else parent[int(token)]
        except (KeyError, IndexError, ValueError, TypeError) as error:
            raise CounterfactualValidationFailed(
                "PERTURB path is unavailable."
            ) from error
    return parent, tokens[-1]


class InMemoryEvidenceValueResolver:
    """Test/local reference resolver; the map is tenant-scoped and never logged."""

    def __init__(
        self, values: Mapping[tuple[str, str, str], Any] | None = None
    ) -> None:
        self._values = dict(values or {})

    def resolve(self, reference: str, context: TenantContext) -> Any:
        try:
            return deepcopy(
                self._values[
                    (context.organization_id, context.project_id or "", reference)
                ]
            )
        except KeyError as error:
            raise EvidenceResolutionFailed("EVIDENCE_RESOLUTION_FAILED") from error

    def register(self, reference: str, value: Any, context: TenantContext) -> None:
        """Register local/demo evidence without persisting it in governance state."""
        self._values[(context.organization_id, context.project_id or "", reference)] = (
            deepcopy(value)
        )

    def digest(self, value: Any) -> str:
        return (
            "sha256:"
            + sha256(
                json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )

    def put_counterfactual(
        self, value: Any, context: TenantContext, provenance: Mapping[str, Any]
    ) -> str:
        reference = f"counterfactual:{self.digest(value)}"
        self._values[(context.organization_id, context.project_id or "", reference)] = (
            deepcopy(value)
        )
        return reference


class GovernedCounterfactualGenerator:
    """Bridge policy/provider construction into Causal Audit without Replay logic."""

    def __init__(
        self,
        policies,
        providers: EvidenceInterventionProviderRegistry,
        resolver: EvidenceValueResolver,
    ) -> None:
        self._policies, self._providers, self._resolver = policies, providers, resolver

    def generate(
        self,
        event,
        strategy: ControlledEvidenceStrategy,
        policy_id: str | None,
        policy_version: int | None,
        seed: int,
        context: TenantContext,
    ) -> CounterfactualEvidence:
        descriptor, policy, provider = self._resolve(
            event, strategy, policy_id, policy_version, context
        )
        reference_only = getattr(provider, "generate_reference_only", None)
        if callable(reference_only):
            return reference_only(descriptor, policy, strategy, seed, context)
        original = self._resolver.resolve(descriptor.evidence_ref, context)
        if self._resolver.digest(original) != descriptor.evidence_digest:
            raise EvidenceResolutionFailed(
                "EVIDENCE_RESOLUTION_FAILED: evidence digest mismatch"
            )
        _, result = provider.generate(
            original, descriptor, policy, strategy, seed, context
        )
        return result

    def validate(
        self,
        event,
        strategy: ControlledEvidenceStrategy,
        policy_id: str | None,
        policy_version: int | None,
        context: TenantContext,
    ) -> None:
        """Validate matching and provider compatibility without resolving evidence."""
        self._resolve(event, strategy, policy_id, policy_version, context)

    def _resolve(
        self,
        event,
        strategy: ControlledEvidenceStrategy,
        policy_id: str | None,
        policy_version: int | None,
        context: TenantContext,
    ) -> tuple[
        ToolEvidenceDescriptor, EvidenceInterventionPolicy, EvidenceInterventionProvider
    ]:
        descriptor = _descriptor(event)
        if policy_id is None:
            try:
                policy = self._policies.resolve_active(descriptor, strategy, context)
            except ValueError as error:
                raise InterventionError(
                    "INTERVENTION_POLICY_NOT_CONFIGURED",
                    code="INTERVENTION_POLICY_NOT_CONFIGURED",
                ) from error
        else:
            try:
                policy = self._policies.get(policy_id, policy_version, context)
            except ValueError as error:
                raise InterventionError(
                    "INTERVENTION_POLICY_NOT_CONFIGURED",
                    code="INTERVENTION_POLICY_NOT_CONFIGURED",
                ) from error
        if policy.status.value != "ACTIVE":
            raise InterventionError(
                "INTERVENTION_POLICY_INACTIVE", code="INTERVENTION_POLICY_INACTIVE"
            )
        if (
            policy.tool_name != descriptor.tool_name
            or policy.schema_id != descriptor.schema_id
            or policy.schema_version != descriptor.schema_version
            or strategy not in policy.allowed_strategies
        ):
            raise InterventionError(
                "UNSUPPORTED_INTERVENTION", code="UNSUPPORTED_INTERVENTION"
            )
        provider = self._providers.resolve(policy)
        if not provider.supports(descriptor, strategy):
            raise UnsupportedEvidenceType("UNSUPPORTED_EVIDENCE_TYPE")
        return descriptor, policy, provider


def _descriptor(event) -> ToolEvidenceDescriptor:
    raw = event.attributes.get("causal_replay")
    descriptor = raw.get("evidence_descriptor") if isinstance(raw, Mapping) else None
    if not isinstance(descriptor, Mapping):
        raise EvidenceSchemaUnavailable("EVIDENCE_SCHEMA_UNAVAILABLE")
    try:
        return ToolEvidenceDescriptor(
            tool_call_id=event.event_id,
            tool_name=str(
                descriptor.get("tool_name")
                or event.attributes.get("tool")
                or event.actor_id
            ),
            evidence_ref=str(descriptor["evidence_ref"]),
            evidence_digest=str(descriptor["evidence_digest"]),
            content_type=str(descriptor["content_type"]),
            schema_id=str(descriptor["schema_id"]),
            schema_version=str(descriptor["schema_version"]),
            replay_adapter_id=str(descriptor["replay_adapter_id"]),
            metadata=descriptor.get("metadata", {}),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EvidenceSchemaUnavailable("EVIDENCE_SCHEMA_UNAVAILABLE") from error
