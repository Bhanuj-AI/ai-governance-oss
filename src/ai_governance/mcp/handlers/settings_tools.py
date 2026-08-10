from __future__ import annotations

import os
from urllib.parse import quote

from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.clients import RestClient
from ai_governance.mcp.dto.requests import (
    SettingsGetRequest,
    SettingsListRequest,
    SettingsUpdateRequest,
    SettingsValidateRequest,
    WriteEnvelope,
)
from ai_governance.mcp.handlers._rest_tool import rest_get
from ai_governance.mcp.observability import MCPMetrics
from ai_governance.mcp.registry import ToolRegistry
from ai_governance.mcp.runtime_context import get_runtime_context
from ai_governance.tenancy.domain import ActorType


def register_settings_tools(
    registry: ToolRegistry,
    client: RestClient,
    metrics: MCPMetrics,
    audit_log: MCPExecutionAuditLog,
) -> None:
    def scoped(request):
        return client.with_tenant_context(
            request.context.organization_id, request.context.project_id
        )

    def actor():
        runtime = get_runtime_context()
        if runtime is not None and runtime.principal is not None:
            return runtime.principal.subject, {
                ActorType.USER: "HUMAN",
                ActorType.SERVICE: "SERVICE",
                ActorType.SYSTEM: "SERVICE",
            }[runtime.principal.principal_type]
        auth_mode = os.getenv("AI_GOVERNANCE_AUTH_MODE").lower()
        if auth_mode == "development":
            administrator_actor_id = os.getenv("AI_GOVERNANCE_DEVELOPMENT_ACTOR_ID")
        elif auth_mode == "keycloak":
            administrator_actor_id = os.getenv("AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB")
            if not administrator_actor_id:
                raise ValueError(
                    "AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB is required when "
                    "AI_GOVERNANCE_AUTH_MODE=keycloak. This value must match the "
                    "Keycloak JWT sub claim for the intended initial administrator."
                )
        else:
            raise ValueError(f"Unsupported authentication mode: {auth_mode}")
        
        return administrator_actor_id, "SERVICE"
    
    def controlled(request, name: str, call):
        requested_by, actor_type = actor()
        envelope = WriteEnvelope(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            requested_by=requested_by,
            actor_type=actor_type,
            reason=request.reason,
            dry_run=request.dry_run,
            context=request.context,
        )
        record = audit_log.start(
            tool_name=name,
            operation_type=name.upper().replace(".", "_"),
            resource_type="setting",
            resource_id=request.key,
            envelope=envelope,
            payload=request.model_dump(mode="json"),
        )
        if request.dry_run:
            result = scoped(request).request(
                "POST",
                "/api/v1/settings/validate",
                body={"key": request.key, "value": request.value},
            )
            audit_log.complete(record, status="DRY_RUN")
            return {"dry_run": True, "validation": result}
        try:
            result = call()
            audit_log.complete(record, status="SUCCEEDED")
            return result
        except Exception as exc:
            audit_log.complete(
                record,
                status="FAILED",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

    registry.register(
        name="settings.list",
        description="List effective platform settings.",
        request_model=SettingsListRequest,
        handler=lambda request: rest_get(
            scoped(request),
            metrics,
            "/api/v1/settings",
            query={"category": request.category, "scope": request.scope},
        ),
    )
    registry.register(
        name="settings.get",
        description="Get one effective platform setting.",
        request_model=SettingsGetRequest,
        handler=lambda request: rest_get(
            scoped(request),
            metrics,
            f"/api/v1/settings/{quote(request.key, safe='')}",
            query={"scope": request.scope},
        ),
    )
    registry.register(
        name="settings.categories",
        description="List setting categories.",
        request_model=SettingsListRequest,
        handler=lambda request: rest_get(
            scoped(request), metrics, "/api/v1/settings/categories"
        ),
    )
    registry.register(
        name="settings.update",
        description="Validate and update a mutable runtime setting.",
        request_model=SettingsUpdateRequest,
        handler=lambda request: controlled(
            request,
            "settings.update",
            lambda: scoped(request).request(
                "PATCH",
                f"/api/v1/settings/{quote(request.key, safe='')}",
                body={
                    "value": request.value,
                    "reason": request.reason,
                    "scope": request.scope,
                    "expected_version": request.expected_version,
                },
            ),
        ),
    )
    registry.register(
        name="settings.validate",
        description="Validate a setting value without persisting it.",
        request_model=SettingsValidateRequest,
        handler=lambda request: controlled(
            request,
            "settings.validate",
            lambda: scoped(request).request(
                "POST",
                "/api/v1/settings/validate",
                body={"key": request.key, "value": request.value},
            ),
        ),
    )
