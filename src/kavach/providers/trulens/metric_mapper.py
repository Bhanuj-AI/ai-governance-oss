from __future__ import annotations

from collections.abc import Iterable

from kavach.evaluation.evaluation_metrics import (
    ANSWER_RELEVANCE,
    CONTEXT_RELEVANCE,
    GROUNDEDNESS,
    SUPPORTED_EVALUATION_METRICS,
    EvaluationMetricSpec,
    normalize_metric_name,
)
from kavach.providers.trulens.errors import UnsupportedTruLensMetricError


class TruLensMetricMapper:
    """
    Maps Kavach metric specs to TruLens-supported metric identifiers.
    """

    def normalize(
        self,
        metric_name: str,
    ) -> str:
        normalized = normalize_metric_name(metric_name)

        if normalized not in SUPPORTED_EVALUATION_METRICS:
            raise UnsupportedTruLensMetricError(
                f"Unsupported TruLens metric '{metric_name}'."
            )

        return normalized

    def map_specs(
        self,
        metric_specs: Iterable[EvaluationMetricSpec] | None = None,
        enabled_metrics: Iterable[str] = (
            ANSWER_RELEVANCE,
            CONTEXT_RELEVANCE,
            GROUNDEDNESS,
        ),
    ) -> list[str]:
        enabled = [
            self.normalize(metric_name)
            for metric_name in enabled_metrics
        ]
        enabled_lookup = set(enabled)

        if not enabled:
            raise UnsupportedTruLensMetricError(
                "No metrics are enabled for TruLens."
            )

        metric_specs = tuple(metric_specs or ())
        if not metric_specs:
            return list(enabled)

        mapped_metrics: list[str] = []
        for metric_spec in metric_specs:
            metric_name = self.normalize(metric_spec.name)
            if metric_name not in enabled_lookup:
                raise UnsupportedTruLensMetricError(
                    f"Requested TruLens metric '{metric_spec.name}' is not "
                    "enabled for this provider configuration."
                )
            if metric_name not in mapped_metrics:
                mapped_metrics.append(metric_name)

        if not mapped_metrics:
            raise UnsupportedTruLensMetricError(
                "No requested metrics are enabled for TruLens."
            )

        return mapped_metrics
