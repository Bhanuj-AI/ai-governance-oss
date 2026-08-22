from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class SettingCategory(str, Enum):
    GENERAL = "General"
    REPOSITORIES = "Repositories"
    JOBS = "Jobs"
    GOVERNANCE = "Governance"
    EVALUATION = "Evaluation"
    ONTOLOGY = "Ontology"
    AUDIT = "Audit"
    MCP = "MCP"
    INTEGRATIONS = "Integrations"
    OBSERVABILITY = "Observability"
    SYSTEM = "System"


class SettingValueType(str, Enum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    DURATION = "DURATION"
    ENUM = "ENUM"
    JSON = "JSON"


class SettingScope(str, Enum):
    SYSTEM = "SYSTEM"
    ORGANIZATION = "ORGANIZATION"
    PROJECT = "PROJECT"


class SettingSource(str, Enum):
    ENVIRONMENT = "ENVIRONMENT"
    RUNTIME_PROJECT = "RUNTIME_PROJECT"
    RUNTIME_ORGANIZATION = "RUNTIME_ORGANIZATION"
    RUNTIME_SYSTEM = "RUNTIME_SYSTEM"
    DEFAULT = "DEFAULT"


@dataclass(frozen=True)
class SettingContext:
    organization_id: str | None = None
    project_id: str | None = None


Validator = Callable[[Any], None]


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    category: SettingCategory
    display_name: str
    description: str
    value_type: SettingValueType
    default_value: Any
    mutable: bool
    sensitive: bool = False
    restart_required: bool = False
    environment_variable: str | None = None
    validator: Validator | None = None
    enum_values: tuple[str, ...] = ()
    allowed_scopes: tuple[SettingScope, ...] = (SettingScope.SYSTEM,)
    runtime_applied: bool = False


@dataclass(frozen=True)
class RuntimeSetting:
    key: str
    scope: SettingScope
    scope_id: str
    value: Any
    version: int
    updated_by: str
    updated_at: datetime


@dataclass(frozen=True)
class SettingAuditRecord:
    audit_id: str
    key: str
    scope: SettingScope
    scope_id: str
    old_value: Any
    new_value: Any
    actor_id: str
    reason: str
    version: int
    created_at: datetime


@dataclass(frozen=True)
class ResolvedSetting:
    definition: SettingDefinition
    edit_scope: SettingScope
    edit_scope_id: str
    runtime_value: Any | None
    effective_value: Any
    source: SettingSource
    inherited_from: SettingScope | None
    version: int | None
    updated_by: str | None
    updated_at: datetime | None


class SettingError(ValueError):
    pass


class SettingNotFound(SettingError):
    pass


class SettingReadOnly(SettingError):
    pass


class SettingEnvironmentOverride(SettingReadOnly):
    pass


class SettingValidationError(SettingError):
    pass


class SettingScopeInvalid(SettingError):
    pass


class SettingVersionConflict(SettingError):
    def __init__(self, key: str, expected_version: int, current_version: int) -> None:
        self.key = key
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"Setting '{key}' changed from expected version {expected_version} "
            f"to {current_version}. Refresh and retry."
        )
