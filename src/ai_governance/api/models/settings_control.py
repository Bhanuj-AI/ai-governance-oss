from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SettingResponse(BaseModel):
    key: str
    display_name: str
    description: str
    category: str
    value_type: str
    value: Any | None
    effective_value: Any
    source: str
    default: Any
    mutable: bool
    editable: bool
    sensitive: bool
    restart_required: bool
    runtime_applied: bool
    allowed_scopes: list[str]
    edit_scope: str
    edit_scope_id: str
    inherited_from: str | None
    environment_variable: str | None
    enum_values: list[str]
    version: int | None
    updated_by: str | None
    updated_at: datetime | None


class SettingUpdateRequest(BaseModel):
    value: Any
    reason: str = Field(min_length=1, max_length=500)
    scope: Literal["SYSTEM", "ORGANIZATION", "PROJECT"] = "SYSTEM"
    expected_version: int = Field(ge=0)


class SettingValidationRequest(BaseModel):
    key: str = Field(min_length=1)
    value: Any


class SettingValidationResponse(BaseModel):
    valid: bool
    parsed_value: Any


class SettingCategoryResponse(BaseModel):
    name: str
    key: str
    setting_count: int


class SettingAuditResponse(BaseModel):
    audit_id: str
    key: str
    scope: str
    scope_id: str
    old_value: Any | None
    new_value: Any
    actor_id: str
    reason: str
    version: int
    created_at: datetime
