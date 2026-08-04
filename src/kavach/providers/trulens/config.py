from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from kavach.evaluation.evaluation_metrics import (
    ANSWER_RELEVANCE,
    CONTEXT_RELEVANCE,
    GROUNDEDNESS,
    normalize_metric_name,
)


@dataclass(frozen=True)
class TruLensConfig:
    openai_api_key: str | None = None
    model: str | None = None
    enabled_metrics: list[str] = field(
        default_factory=lambda: [
            ANSWER_RELEVANCE,
            CONTEXT_RELEVANCE,
            GROUNDEDNESS,
        ]
    )
    timeout_seconds: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "enabled_metrics",
            [
                normalize_metric_name(metric)
                for metric in self.enabled_metrics
            ],
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
    ) -> TruLensConfig:
        return cls(
            openai_api_key=values.get("openai_api_key"),
            model=values.get("model"),
            enabled_metrics=list(
                values.get(
                    "enabled_metrics",
                    [
                        ANSWER_RELEVANCE,
                        CONTEXT_RELEVANCE,
                        GROUNDEDNESS,
                    ],
                )
            ),
            timeout_seconds=values.get("timeout_seconds"),
            metadata=values.get("metadata", {}),
        )

    @classmethod
    def from_environment(cls) -> TruLensConfig:
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model=(
                os.getenv("KAVACH_TRULENS_MODEL")
                or os.getenv("OPENAI_DEFAULT_JUDGE_MODEL")
            ),
        )

    def overlay(
        self,
        values: Mapping[str, Any],
    ) -> TruLensConfig:
        if not values:
            return self

        return TruLensConfig(
            openai_api_key=values.get("openai_api_key", self.openai_api_key),
            model=values.get("model", self.model),
            enabled_metrics=list(
                values.get("enabled_metrics", self.enabled_metrics)
            ),
            timeout_seconds=values.get(
                "timeout_seconds",
                self.timeout_seconds,
            ),
            metadata={
                **dict(self.metadata),
                **dict(values.get("metadata", {})),
            },
        )
