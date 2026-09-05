"""Composition root and value parser for settings control."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from types import MappingProxyType
from typing import Any

from .definitions import OSS_SETTING_DEFINITION_SETS
from .domain import SettingDefinition, SettingValidationError
from .domain import SettingValueType as T


def _compose_definitions(
    definition_sets: Iterable[tuple[SettingDefinition, ...]],
) -> dict[str, SettingDefinition]:
    """Compose independently owned built-in definitions with duplicate safety."""
    definitions: dict[str, SettingDefinition] = {}
    for definition_set in definition_sets:
        for definition in definition_set:
            if definition.key in definitions:
                raise ValueError(
                    f"Duplicate built-in setting definition: '{definition.key}'."
                )
            definitions[definition.key] = definition
    return definitions


_SETTINGS = _compose_definitions(OSS_SETTING_DEFINITION_SETS)
SETTINGS_REGISTRY = MappingProxyType(_SETTINGS)


def register_extension_definitions(definitions) -> None:
    """Register validated plugin settings before configuration services run."""
    for definition in definitions:
        if not isinstance(definition, SettingDefinition):
            raise TypeError("Plugin settings must be SettingDefinition instances.")
        if definition.key in _SETTINGS:
            raise ValueError(f"Setting '{definition.key}' is already registered.")
        _SETTINGS[definition.key] = definition


def parse_value(definition: SettingDefinition, value: Any) -> Any:
    try:
        if definition.value_type is T.STRING:
            parsed = str(value)
        elif definition.value_type is T.INTEGER:
            parsed = int(value)
        elif definition.value_type is T.FLOAT:
            parsed = float(value)
        elif definition.value_type is T.BOOLEAN:
            if isinstance(value, bool):
                parsed = value
            elif str(value).strip().lower() in {"1", "true", "yes", "on"}:
                parsed = True
            elif str(value).strip().lower() in {"0", "false", "no", "off"}:
                parsed = False
            else:
                raise ValueError("expected a boolean")
        elif definition.value_type is T.JSON:
            parsed = json.loads(value) if isinstance(value, str) else value
        elif definition.value_type is T.DURATION:
            parsed = str(value).strip().lower()
            if not re.fullmatch(r"[1-9][0-9]*(ms|s|m|h|d|w)", parsed):
                raise ValueError("expected a duration such as 30s, 5m, 24h, or 30d")
        elif definition.value_type is T.ENUM:
            parsed = str(value).strip().lower()
            if parsed not in definition.enum_values:
                raise ValueError(
                    f"expected one of: {', '.join(definition.enum_values)}"
                )
        else:
            parsed = value
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SettingValidationError(
            f"Invalid value for '{definition.key}': {exc}"
        ) from exc
    if definition.validator:
        definition.validator(parsed)
    return parsed
