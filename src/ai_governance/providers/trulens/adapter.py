from __future__ import annotations

import time
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from packaging.version import InvalidVersion, Version
from trulens.providers.openai import OpenAI  # type: ignore

from ai_governance.domain.evaluation_dataset import EvaluationDataset
from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation.evaluation_metrics import (
    ANSWER_RELEVANCE,
    CONTEXT_RELEVANCE,
    GROUNDEDNESS,
)
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.providers.evaluation_provider import EvaluationProvider
from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.providers.schema_loader import load_provider_configuration_schema
from ai_governance.providers.trulens.config import TruLensConfig
from ai_governance.providers.trulens.errors import TruLensProviderError
from ai_governance.providers.trulens.metric_mapper import TruLensMetricMapper
from ai_governance.providers.trulens.result_mapper import TruLensResultMapper


class TruLensAdapter(EvaluationProvider):
    """
    TruLens evaluation adapter behind AI Governance Control Plane's provider contract.
    """

    def __init__(
        self,
        llm_provider: OpenAI | None = None,
        judge_model: str | None = None,
        config: TruLensConfig | None = None,
        metric_mapper: TruLensMetricMapper | None = None,
        result_mapper: TruLensResultMapper | None = None,
    ) -> None:
        self._explicit_provider = llm_provider
        self._explicit_config = config
        self._judge_model = judge_model
        self._metric_mapper = metric_mapper or TruLensMetricMapper()
        self._result_mapper = result_mapper or TruLensResultMapper()

    @property
    def descriptor(self) -> ProviderDescriptor:
        config = self._explicit_config or TruLensConfig.from_environment()
        model = self._judge_model or config.model

        return ProviderDescriptor(
            name="trulens",
            display_name="TruLens",
            version=self._provider_version(),
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=(
                    ANSWER_RELEVANCE,
                    CONTEXT_RELEVANCE,
                    GROUNDEDNESS,
                ),
                supported_evaluation_modes=("sync",),
                supports_batch=False,
                supports_async=False,
                supports_artifacts=True,
                supports_explanations=True,
                supports_row_level_results=False,
            ),
            configuration_schema=load_provider_configuration_schema("trulens"),
            metadata={
                "judge_model": model,
            },
        )

    def validate_configuration(self, provider_config: Mapping[str, Any]) -> None:
        """Verify that the resolved configuration can initialize a judge client."""
        self._provider(self._resolve_config(provider_config))

    @property
    def provider_metadata(self) -> dict[str, Any]:
        return self._result_mapper.safe_metadata(
            {
                "provider": self.descriptor.name,
                "provider_version": self.descriptor.version,
                "adapter_version": self.descriptor.adapter_version,
                **dict(self.descriptor.metadata),
            }
        )

    def evaluate(
        self,
        request: EvaluationRequest | EvaluationDataset,
    ) -> EvaluationResult:
        normalized_request = self._normalize_request(request)
        config = self._resolve_config(normalized_request.provider_config)
        provider = self._provider(config)
        metric_names = self._metric_mapper.map_specs(
            normalized_request.metric_specs,
            config.enabled_metrics,
        )

        raw_result = self._evaluate_metrics(
            provider=provider,
            request=normalized_request,
            metric_names=metric_names,
        )

        return self._result_mapper.to_evaluation_result(
            request=normalized_request,
            raw_result=raw_result,
            provider_metadata=self._metadata_for_config(config),
        )

    def _evaluate_metrics(
        self,
        provider: OpenAI,
        request: EvaluationRequest,
        metric_names: list[str],
    ) -> dict[str, Any]:
        metrics: list[dict[str, Any]] = []
        timings: dict[str, float] = {}
        dataset = request.dataset

        for metric_name in metric_names:
            if metric_name in (CONTEXT_RELEVANCE, GROUNDEDNESS) and not dataset.context_text:
                continue

            started_at = time.perf_counter()

            if metric_name == ANSWER_RELEVANCE:
                value, explanation = _score_and_explanation(provider.relevance(
                    prompt=dataset.input_text,
                    response=dataset.output_text,
                ))
            elif metric_name == CONTEXT_RELEVANCE:
                value, explanation = _score_and_explanation(provider.context_relevance(
                    question=dataset.input_text,
                    context=dataset.context_text,
                ))
            elif metric_name == GROUNDEDNESS:
                value, explanation = _score_and_explanation(
                    provider.groundedness_measure_with_cot_reasons(
                        source=dataset.context_text,
                        statement=dataset.output_text,
                    )
                )
            else:
                raise TruLensProviderError(
                    f"Metric '{metric_name}' was not mapped to TruLens."
                )

            timings[metric_name] = time.perf_counter() - started_at
            metrics.append(
                {
                    "name": metric_name,
                    "value": float(value),
                    "explanation": str(explanation)
                    if explanation is not None
                    else None,
                }
            )

        return {
            "metrics": metrics,
            "timings": timings,
        }

    def _resolve_config(
        self,
        request_provider_config: Mapping[str, Any],
    ) -> TruLensConfig:
        config = TruLensConfig.from_environment()
        config = config.overlay(request_provider_config)

        if self._explicit_config is not None:
            config = config.overlay(
                {
                    "openai_api_key": self._explicit_config.openai_api_key,
                    "model": self._explicit_config.model,
                    "enabled_metrics": self._explicit_config.enabled_metrics,
                    "timeout_seconds": self._explicit_config.timeout_seconds,
                    "metadata": self._explicit_config.metadata,
                }
            )

        if self._judge_model is not None:
            config = config.overlay({"model": self._judge_model})

        return config

    def _provider(
        self,
        config: TruLensConfig,
    ) -> OpenAI:
        if self._explicit_provider is not None:
            return self._explicit_provider

        self._require_supported_openai_provider_version()

        if config.model is None:
            raise TruLensProviderError(
                "TruLens requires a model via TruLensConfig, "
                "request.provider_config, or AI_GOVERNANCE_TRULENS_MODEL."
            )

        return OpenAI(
            model_engine=config.model,
            api_key=config.openai_api_key,
            max_retries=0,
        )

    @staticmethod
    def _require_supported_openai_provider_version() -> None:
        """Reject the known-bad OpenAI Responses API score parser early.

        TruLens 2.8.1 serializes a ``custom_tool_call`` response and then
        extracts a score by scanning that entire JSON payload. This can record
        an unrelated number as the evaluator score and logs the protected raw
        response. TruLens 2.10.0 fixes extraction from the tool-call input.
        """
        try:
            installed_version = Version(version("trulens-providers-openai"))
        except PackageNotFoundError as exc:
            raise TruLensProviderError(
                "TruLens OpenAI provider is not installed. Install "
                "trulens-providers-openai>=2.10.0."
            ) from exc
        except InvalidVersion as exc:
            raise TruLensProviderError(
                "TruLens OpenAI provider has an invalid installed version. "
                "Install trulens-providers-openai>=2.10.0."
            ) from exc

        if installed_version < Version("2.10.0"):
            raise TruLensProviderError(
                "TruLens OpenAI provider "
                f"{installed_version} is unsupported for OpenAI Responses API scoring. "
                "Upgrade trulens and trulens-providers-openai to >=2.10.0."
            )

    def _metadata_for_config(
        self,
        config: TruLensConfig,
    ) -> dict[str, Any]:
        return self._result_mapper.safe_metadata(
            {
                "provider": self.descriptor.name,
                "provider_version": self.descriptor.version,
                "adapter_version": self.descriptor.adapter_version,
                "judge_model": config.model,
                "enabled_metrics": list(config.enabled_metrics),
                "timeout_seconds": config.timeout_seconds,
                **dict(config.metadata),
            }
        )

    @staticmethod
    def _provider_version() -> str:
        try:
            return version("trulens")
        except PackageNotFoundError:
            return "unknown"

    @staticmethod
    def _normalize_request(
        request: EvaluationRequest | EvaluationDataset,
    ) -> EvaluationRequest:
        if isinstance(request, EvaluationRequest):
            return request

        return EvaluationRequest(
            execution=WorkflowExecution(
                workflow_id=request.execution_id,
                execution_id=request.execution_id,
                workflow_name="unknown",
                workflow_version="unknown",
                execution_status="COMPLETED",
                input={},
                final_state={},
                events=[],
            ),
            dataset=request,
            provider_config={},
        )


def _score_and_explanation(value: Any) -> tuple[float, Any | None]:
    """Normalize TruLens scalar and ``(score, reason)`` feedback results."""

    if isinstance(value, tuple):
        if not value:
            raise TruLensProviderError("TruLens returned an empty feedback result.")
        score, *details = value
        return float(score), details[0] if details else None
    return float(value), None
