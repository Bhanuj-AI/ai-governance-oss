from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ai_governance.api.dependencies.authorization import enforce_permission
from ai_governance.api.dependencies.settings_control import (
    get_configuration_service,
    get_settings_repository,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.models.settings_control import (
    SettingAuditResponse,
    SettingCategoryResponse,
    SettingResponse,
    SettingUpdateRequest,
    SettingValidationRequest,
    SettingValidationResponse,
)
from ai_governance.settings_control.domain import (
    ResolvedSetting,
    SettingContext,
    SettingError,
    SettingScope,
    SettingVersionConflict,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.permissions import Permission

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


def _response(item: ResolvedSetting) -> SettingResponse:
    definition = item.definition
    return SettingResponse(
        key=definition.key,
        display_name=definition.display_name,
        description=definition.description,
        category=definition.category.value,
        value_type=definition.value_type.value,
        value=item.runtime_value,
        effective_value=item.effective_value,
        source=item.source.value,
        default=definition.default_value,
        mutable=definition.mutable,
        editable=(
            definition.mutable
            and definition.runtime_applied
            and item.source.value != "ENVIRONMENT"
        ),
        sensitive=definition.sensitive,
        restart_required=definition.restart_required,
        runtime_applied=definition.runtime_applied,
        allowed_scopes=[scope.value for scope in definition.allowed_scopes],
        edit_scope=item.edit_scope.value,
        edit_scope_id=item.edit_scope_id,
        inherited_from=item.inherited_from.value if item.inherited_from else None,
        environment_variable=definition.environment_variable,
        enum_values=list(definition.enum_values),
        version=item.version,
        updated_by=item.updated_by,
        updated_at=item.updated_at,
    )


def _bad_request(exc: SettingError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": exc.__class__.__name__.upper(), "message": str(exc)},
    )


@router.get("", response_model=list[SettingResponse])
def list_settings(
    category: str | None = Query(default=None),
    scope: SettingScope = Query(default=SettingScope.SYSTEM),
    context: TenantContext = Depends(get_compatible_tenant_context),
    service=Depends(get_configuration_service),
):
    setting_context = SettingContext(context.organization_id, context.project_id)
    return [_response(item) for item in service.list(category, setting_context, scope)]


@router.get("/categories", response_model=list[SettingCategoryResponse])
def list_setting_categories(service=Depends(get_configuration_service)):
    return service.categories()


@router.get("/audit", response_model=list[SettingAuditResponse])
def list_setting_audit(
    key: str | None = Query(default=None),
    scope: SettingScope | None = Query(default=None),
    context: TenantContext = Depends(get_compatible_tenant_context),
    repository=Depends(get_settings_repository),
):
    scope_id = None
    if scope is SettingScope.SYSTEM:
        scope_id = ""
    elif scope is SettingScope.ORGANIZATION:
        scope_id = context.organization_id
    elif scope is SettingScope.PROJECT:
        scope_id = context.project_id
    return repository.list_audit(key, scope, scope_id)


@router.post("/validate", response_model=SettingValidationResponse)
def validate_setting(
    request: SettingValidationRequest, service=Depends(get_configuration_service)
):
    try:
        return SettingValidationResponse(
            valid=True, parsed_value=service.validate(request.key, request.value)
        )
    except SettingError as exc:
        raise _bad_request(exc) from exc


@router.get("/{key:path}", response_model=SettingResponse)
def get_setting(
    key: str,
    scope: SettingScope = Query(default=SettingScope.SYSTEM),
    context: TenantContext = Depends(get_compatible_tenant_context),
    service=Depends(get_configuration_service),
):
    try:
        return _response(
            service.resolve(
                key,
                SettingContext(context.organization_id, context.project_id),
                scope,
            )
        )
    except SettingError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "SETTING_NOT_FOUND", "message": str(exc)}
        ) from exc


@router.patch("/{key:path}", response_model=SettingResponse)
def update_setting(
    key: str,
    request: SettingUpdateRequest,
    context: TenantContext = Depends(get_compatible_tenant_context),
    service=Depends(get_configuration_service),
    _=Depends(enforce_permission(Permission.SETTINGS_MANAGE)),
):
    try:
        return _response(
            service.update(
                key,
                request.value,
                context.actor_id,
                request.reason,
                request.expected_version,
                SettingScope(request.scope),
                SettingContext(context.organization_id, context.project_id),
                context,
            )
        )
    except SettingVersionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SETTING_VERSION_CONFLICT",
                "message": str(exc),
                "current_version": exc.current_version,
            },
        ) from exc
    except SettingError as exc:
        raise _bad_request(exc) from exc
