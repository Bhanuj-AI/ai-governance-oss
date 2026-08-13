from __future__ import annotations

import logging
import os
from contextlib import suppress
from threading import Thread
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore

from ai_governance.api.demo_seed import seed_demo_data_for_app
from ai_governance.api.dependencies import get_api_settings
from ai_governance.api.exception_handlers import register_exception_handlers
from ai_governance.api.logging import (
    configure_sensitive_third_party_logging,
    formatter_for,
    request_logging_middleware,
)
from ai_governance.api.dependencies.authorization import (
    enforce_permission,
    enforce_policy_permission,
    enforce_replay_permission,
    enforce_read_write,
)
from ai_governance.tenancy.permissions import Permission
from ai_governance.api.routers import (
    audit_router,
    datasets_router,
    dashboard_router,
    decisions_router,
    evaluations_router,
    experiments_router,
    extensions_router,
    governance_router,
    health_router,
    investigations_router,
    jobs_router,
    local_demo_router,
    mcp_audit_router,
    metadata_router,
    models_router,
    ontology_graph_router,
    ontology_sync_router,
    policies_router,
    prompts_router,
    providers_router,
    provider_installations_router,
    reports_router,
    replay_executions_router,
    replays_router,
    runtime_connections_router,
    settings_router,
    telemetry_router,
    tenancy_router,
)
from ai_governance.plugins import AIGovernancePlugin, PluginRegistry, create_plugin_registry
from ai_governance.api.dependencies.telemetry import install_telemetry
from ai_governance.services.telemetry_service import TelemetryDeliveryWorker


def _configure_application_logging(log_level: str, log_format: str = "json") -> None:
    """Route application logs to stderr when Uvicorn owns the process.

    Uvicorn configures handlers for its own ``uvicorn.*`` namespaces but not
    for application loggers. Without an explicit handler, progress records
    from services are silently discarded even when
    ``AI_GOVERNANCE_API_LOG_LEVEL=debug`` is configured.
    """

    application_logger = logging.getLogger("ai_governance")
    application_logger.setLevel(log_level.upper())
    application_logger.propagate = False
    handler = next(
        (
            candidate
            for candidate in application_logger.handlers
            if getattr(candidate, "_ai_governance_application_handler", False)
        ),
        None,
    )

    if handler is None:
        handler = logging.StreamHandler()
        handler._ai_governance_application_handler = True  # type: ignore[attr-defined]
        application_logger.addHandler(handler)
    handler.setFormatter(formatter_for(log_format))
    configure_sensitive_third_party_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_api_settings()
    if settings.auto_seed_demo_data:
        seed_demo_data_for_app(app)
    extension_registry: PluginRegistry = app.state.extension_registry
    extension_registry.start()
    replay_worker = None
    worker_thread = None
    telemetry_worker = TelemetryDeliveryWorker(app.state.telemetry_service)
    telemetry_thread = Thread(
        target=telemetry_worker.run_forever,
        name="ai-governance-telemetry-worker",
        daemon=True,
    )
    telemetry_thread.start()
    if os.getenv("AI_GOVERNANCE_RUN_REPLAY_WORKER", "false").lower() == "true":
        from ai_governance.workers.replay_worker_runtime import create_replay_worker_runtime

        replay_worker = create_replay_worker_runtime(
            event_publisher=extension_registry.events
        )
        worker_thread = Thread(
            target=replay_worker.run_forever,
            name="ai-governance-replay-worker",
            daemon=True,
        )
        worker_thread.start()
    try:
        yield
    finally:
        extension_registry.stop()
        if replay_worker is not None:
            replay_worker.stop()
        if worker_thread is not None:
            with suppress(RuntimeError):
                worker_thread.join(timeout=5)
        telemetry_worker.stop()
        with suppress(RuntimeError):
            telemetry_thread.join(timeout=5)


def create_app(*, plugins: Iterable[AIGovernancePlugin] = ()) -> FastAPI:
    """
    Create and configure the AI Governance Control Plane REST API application.
    """

    settings = get_api_settings()
    _configure_application_logging(settings.log_level, settings.log_format)
    logging.getLogger("ai_governance.api").setLevel(settings.log_level.upper())
    if settings.identity_provider == "development":
        logging.getLogger("ai_governance.api").critical(
            "Development identity provider is enabled; do not use it for production authentication."
        )
    logging.getLogger("ai_governance.api").info(
        "authentication_mode",
        extra={"auth_mode": settings.auth_mode},
    )

    app = FastAPI(
        title="AI Governance Control Plane REST API",
        description="AI Governance Control Plane for Enterprise LLMs",
        version="v1",
        lifespan=lifespan,
    )
    extension_registry = create_plugin_registry(plugins=plugins)
    app.state.extension_registry = extension_registry
    app.state.plugin_metrics = {}
    extension_registry.contributions.install(app)
    install_telemetry(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.middleware("http")(request_logging_middleware)
    app.include_router(health_router)
    app.include_router(metadata_router)
    app.include_router(extensions_router)
    app.include_router(
        audit_router, dependencies=[Depends(enforce_permission(Permission.AUDIT_READ))]
    )
    app.include_router(
        dashboard_router,
        dependencies=[Depends(enforce_permission(Permission.AUDIT_READ))],
    )
    app.include_router(providers_router)
    app.include_router(
        provider_installations_router,
        dependencies=[
            Depends(
                enforce_read_write(
                    Permission.EVALUATION_READ, Permission.SETTINGS_MANAGE
                )
            )
        ],
    )
    app.include_router(
        runtime_connections_router,
        dependencies=[
            Depends(
                enforce_read_write(
                    Permission.EVALUATION_READ, Permission.RUNTIME_CONNECTION_MANAGE
                )
            )
        ],
    )
    app.include_router(
        prompts_router,
        dependencies=[
            Depends(
                enforce_read_write(Permission.POLICY_READ, Permission.POLICY_UPDATE)
            )
        ],
    )
    app.include_router(
        models_router,
        dependencies=[
            Depends(
                enforce_read_write(Permission.POLICY_READ, Permission.POLICY_UPDATE)
            )
        ],
    )
    app.include_router(
        ontology_graph_router,
        dependencies=[Depends(enforce_permission(Permission.ONTOLOGY_READ))],
    )
    app.include_router(
        ontology_sync_router,
        dependencies=[
            Depends(
                enforce_read_write(
                    Permission.ONTOLOGY_READ, Permission.ONTOLOGY_SYNCHRONIZE
                )
            )
        ],
    )
    app.include_router(
        policies_router, dependencies=[Depends(enforce_policy_permission)]
    )
    app.include_router(
        datasets_router,
        dependencies=[
            Depends(
                enforce_read_write(
                    Permission.EVALUATION_READ, Permission.EVALUATION_EXECUTE
                )
            )
        ],
    )
    app.include_router(
        decisions_router,
        dependencies=[
            Depends(
                enforce_read_write(
                    Permission.DECISION_READ, Permission.DECISION_EVALUATE
                )
            )
        ],
    )
    app.include_router(
        evaluations_router,
        dependencies=[
            Depends(
                enforce_read_write(
                    Permission.EVALUATION_READ, Permission.EVALUATION_EXECUTE
                )
            )
        ],
    )
    app.include_router(
        experiments_router,
        dependencies=[
            Depends(
                enforce_read_write(
                    Permission.EVALUATION_READ, Permission.EVALUATION_EXECUTE
                )
            )
        ],
    )
    app.include_router(
        governance_router,
        dependencies=[
            Depends(
                enforce_read_write(
                    Permission.DECISION_READ, Permission.DECISION_EVALUATE
                )
            )
        ],
    )
    app.include_router(
        replay_executions_router, dependencies=[Depends(enforce_replay_permission)]
    )
    app.include_router(
        replays_router, dependencies=[Depends(enforce_replay_permission)]
    )
    app.include_router(jobs_router)
    app.include_router(
        local_demo_router,
        dependencies=[Depends(enforce_permission(Permission.SETTINGS_MANAGE))],
    )
    app.include_router(
        mcp_audit_router,
        dependencies=[Depends(enforce_permission(Permission.MCP_AUDIT_READ))],
    )
    app.include_router(
        investigations_router,
        dependencies=[Depends(enforce_permission(Permission.AUDIT_READ))],
    )
    app.include_router(
        reports_router,
        dependencies=[Depends(enforce_permission(Permission.AUDIT_READ))],
    )
    app.include_router(tenancy_router)
    app.include_router(
        settings_router,
        dependencies=[
            Depends(
                enforce_read_write(Permission.SETTINGS_READ, Permission.SETTINGS_MANAGE)
            )
        ],
    )
    app.include_router(
        telemetry_router,
        dependencies=[Depends(enforce_permission(Permission.SETTINGS_READ))],
    )

    # Contributions are installed only after core routes have claimed their
    # paths, making route collisions and unauthorized replacements fail fast.
    extension_registry.routes.install(app)

    return app


app = create_app()
