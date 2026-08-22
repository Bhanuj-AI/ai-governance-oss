"""Shared construction and validation helpers for built-in setting modules."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ai_governance.domain.models import (
    known_runtime_model_provider_keys,
    runtime_model_provider_key,
)
from ai_governance.settings_control.domain import (
    SettingCategory as Category,
)
from ai_governance.settings_control.domain import (
    SettingDefinition,
    SettingScope,
    SettingValidationError,
)
from ai_governance.settings_control.domain import (
    SettingValueType as ValueType,
)


def range_validator(minimum: float, maximum: float):
    def validate(value: Any) -> None:
        if not minimum <= value <= maximum:
            raise SettingValidationError(
                f"Value must be between {minimum:g} and {maximum:g}."
            )

    return validate


def non_empty(value: Any) -> None:
    if not str(value).strip():
        raise SettingValidationError("Value must not be blank.")


def https_url(value: Any) -> None:
    parsed = urlparse(str(value))
    if parsed.scheme != "https" or not parsed.netloc:
        raise SettingValidationError("Expected an HTTPS URL.")


def optional_env_secret_reference(value: Any) -> None:
    reference = str(value).strip()
    if reference and not reference.startswith("env://"):
        raise SettingValidationError("Expected an env:// secret reference.")


def synthesizer_pricing(value: Any) -> None:
    if not isinstance(value, dict):
        raise SettingValidationError("Expected a model-to-pricing JSON object.")
    for model, rates in value.items():
        if not isinstance(model, str) or not model.strip() or not isinstance(rates, dict):
            raise SettingValidationError(
                "Each pricing entry requires a model name and rate object."
            )
        for key in ("input", "cached_input", "output"):
            rate = rates.get(key)
            if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate < 0:
                raise SettingValidationError(
                    f"Pricing for '{model}' must include a non-negative '{key}' rate."
                )


def runtime_model_provider_allow_list(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise SettingValidationError(
            "Expected a non-empty JSON array of runtime provider keys."
        )
    if not all(isinstance(provider, str) for provider in value):
        raise SettingValidationError(
            "Each runtime provider must be a canonical built-in provider key."
        )
    if len(value) != len(set(value)):
        raise SettingValidationError("Runtime provider keys must not be repeated.")
    for provider in value:
        if (
            provider not in known_runtime_model_provider_keys()
            or runtime_model_provider_key(provider) != provider
        ):
            raise SettingValidationError(
                "Each runtime provider must be a canonical built-in provider key."
            )


def definition(
    key: str,
    category: Category,
    name: str,
    description: str,
    value_type: ValueType,
    default: Any,
    *,
    mutable: bool = True,
    env: str | None = None,
    restart: bool = False,
    validator=None,
    enum: tuple[str, ...] = (),
    sensitive: bool = False,
    scopes: tuple[SettingScope, ...] | None = None,
    runtime_applied: bool = False,
) -> SettingDefinition:
    return SettingDefinition(
        key,
        category,
        name,
        description,
        value_type,
        default,
        mutable,
        sensitive,
        restart,
        env,
        validator,
        enum,
        scopes
        if scopes is not None
        else (
            (SettingScope.SYSTEM, SettingScope.ORGANIZATION, SettingScope.PROJECT)
            if mutable
            else (SettingScope.SYSTEM,)
        ),
        runtime_applied,
    )
