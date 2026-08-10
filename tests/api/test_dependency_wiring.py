"""
Wiring smoke tests for the split dependency package.

These tests verify that core providers still resolve correctly after the
refactor and that cached repository providers behave as singletons.
"""

from __future__ import annotations


def test_get_api_settings_resolves() -> None:
    from ai_governance.api.dependencies import get_api_settings

    settings = get_api_settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_get_provider_registry_resolves() -> None:
    from ai_governance.api.dependencies import get_provider_registry

    registry = get_provider_registry()
    assert registry is not None


def test_get_provider_registry_registers_only_mock_without_trulens_configuration(
    monkeypatch,
) -> None:
    from ai_governance.api.dependencies import get_provider_registry

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_GOVERNANCE_TRULENS_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_DEFAULT_JUDGE_MODEL", raising=False)

    registry = get_provider_registry()

    assert registry.contains("mock")
    assert not registry.contains("trulens")


def test_get_provider_registry_registers_trulens_with_openai_configuration(
    monkeypatch,
) -> None:
    from ai_governance.api.dependencies import get_provider_registry

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("AI_GOVERNANCE_TRULENS_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_DEFAULT_JUDGE_MODEL", "gpt-4o-mini")

    registry = get_provider_registry()

    assert registry.contains("mock")
    assert registry.contains("trulens")
    assert registry.get("trulens").descriptor.metadata["judge_model"] == "gpt-4o-mini"


def test_get_evaluation_repository_resolves() -> None:
    from ai_governance.api.dependencies import get_evaluation_repository

    get_evaluation_repository.cache_clear()
    repo = get_evaluation_repository()
    assert repo is not None


def test_get_experiment_repository_resolves() -> None:
    from ai_governance.api.dependencies import get_experiment_repository

    get_experiment_repository.cache_clear()
    repo = get_experiment_repository()
    assert repo is not None


def test_get_job_repository_resolves() -> None:
    from ai_governance.api.dependencies import get_job_repository

    get_job_repository.cache_clear()
    repo = get_job_repository()
    assert repo is not None


def test_get_ontology_sync_event_publisher_resolves() -> None:
    from ai_governance.api.dependencies import get_ontology_sync_event_publisher

    publisher = get_ontology_sync_event_publisher()
    assert publisher is not None


def test_get_mcp_audit_log_resolves() -> None:
    from ai_governance.api.dependencies import get_mcp_audit_log

    log = get_mcp_audit_log()
    assert log is not None


def test_get_mcp_audit_log_uses_postgres_when_configured(monkeypatch) -> None:
    from ai_governance.api.dependencies import get_mcp_audit_log
    from ai_governance.mcp.audit import MCPExecutionAuditLog

    expected = MCPExecutionAuditLog.in_memory()
    monkeypatch.setenv("AI_GOVERNANCE_MCP_AUDIT_REPOSITORY", "postgres")
    monkeypatch.setenv("AI_GOVERNANCE_MCP_AUDIT_POSTGRES_DSN", "postgresql://audit@db/ai-governance")
    monkeypatch.setattr(
        MCPExecutionAuditLog,
        "postgres",
        classmethod(lambda _cls, _dsn: expected),
    )
    get_mcp_audit_log.cache_clear()
    try:
        assert get_mcp_audit_log() is expected
    finally:
        get_mcp_audit_log.cache_clear()


def test_get_audit_read_service_resolves() -> None:
    from ai_governance.api.dependencies import get_audit_read_service

    service = get_audit_read_service()
    assert service is not None


def test_get_governance_decision_repository_resolves() -> None:
    from ai_governance.api.dependencies import get_governance_decision_repository

    get_governance_decision_repository.cache_clear()
    repo = get_governance_decision_repository()
    assert repo is not None


def test_get_policy_administration_repository_resolves() -> None:
    from ai_governance.api.dependencies import get_policy_administration_repository

    get_policy_administration_repository.cache_clear()
    repo = get_policy_administration_repository()
    assert repo is not None


def test_get_ontology_graph_query_service_resolves() -> None:
    from ai_governance.api.dependencies import get_ontology_graph_query_service

    service = get_ontology_graph_query_service()
    assert service is not None


def test_cached_repository_providers_are_singletons() -> None:
    """Cached repository providers must return the same instance."""

    from ai_governance.api.dependencies import get_job_repository

    get_job_repository.cache_clear()
    assert get_job_repository() is get_job_repository()


def test_cached_evaluation_repository_is_singleton() -> None:
    from ai_governance.api.dependencies import get_evaluation_repository

    get_evaluation_repository.cache_clear()
    assert get_evaluation_repository() is get_evaluation_repository()


def test_cached_experiment_repository_is_singleton() -> None:
    from ai_governance.api.dependencies import get_experiment_repository

    get_experiment_repository.cache_clear()
    assert get_experiment_repository() is get_experiment_repository()


def test_evaluation_api_service_resolves() -> None:
    from ai_governance.api.dependencies import get_evaluation_api_service

    service = get_evaluation_api_service()
    assert service is not None


def test_experiment_api_service_resolves() -> None:
    from ai_governance.api.dependencies import get_experiment_api_service

    service = get_experiment_api_service()
    assert service is not None


def test_governance_decision_application_service_resolves() -> None:
    from ai_governance.api.dependencies import get_governance_decision_application_service

    service = get_governance_decision_application_service()
    assert service is not None


def test_dashboard_read_service_resolves() -> None:
    from ai_governance.api.dependencies import get_dashboard_read_service

    service = get_dashboard_read_service()
    assert service is not None


def test_governance_report_service_resolves() -> None:
    from ai_governance.api.dependencies import get_governance_report_service

    service = get_governance_report_service()
    assert service is not None
