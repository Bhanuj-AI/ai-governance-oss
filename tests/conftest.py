"""
Pytest configuration.

Sets default environment variables for all tests. This ensures tests run with
the same configuration as the local development environment without hardcoding
defaults in os.getenv() calls.

Overrides Docker-specific paths (like /var/lib/ai-governance) with local paths
for the test environment.
"""

from __future__ import annotations

import os

import pytest

# Set default environment variables for tests
_defaults = {
    # AI Governance Control Plane Configuration
    "AI_GOVERNANCE_ENV": "local",
    "AI_GOVERNANCE_CORS_ALLOW_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
    "AI_GOVERNANCE_AUTO_SEED_DEMO_DATA": "true",
    "AI_GOVERNANCE_API_LOG_LEVEL": "debug",
    "AI_GOVERNANCE_API_HOST": "localhost",
    "AI_GOVERNANCE_API_PORT": "8000",

    # IDP Configuration
    "AI_GOVERNANCE_AUTH_MODE": "development",
    "AI_GOVERNANCE_IDENTITY_PROVIDER": "development",
    "AI_GOVERNANCE_DEVELOPMENT_ACTOR_ID": "local-admin",
    "AI_GOVERNANCE_DEVELOPMENT_ACTOR_NAME": "Local Administrator",
    "AI_GOVERNANCE_OIDC_ISSUER": "http://localhost:8080/realms/ai-governance",
    "AI_GOVERNANCE_OIDC_JWKS_REFRESH_SECONDS": "300",

    # RBAC & Multi-Tenant Configuration
    "AI_GOVERNANCE_ALLOW_DEVELOPMENT_IDENTITY_IN_PRODUCTION": "false",
    "AI_GOVERNANCE_TENANCY_ENABLED": "true",

    # Bootstrap Configuration
    "AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID": "org_default",
    "AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_NAME": "Default Organization",
    "AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_SLUG": "default",
    "AI_GOVERNANCE_BOOTSTRAP_PROJECT_ID": "project_default",
    "AI_GOVERNANCE_BOOTSTRAP_PROJECT_NAME": "Default Project",
    "AI_GOVERNANCE_BOOTSTRAP_PROJECT_SLUG": "default",

    # Graph DB Configuration
    "AI_GOVERNANCE_GRAPH_URI": "bolt://neo4j:7687",
    "AI_GOVERNANCE_GRAPH_USER": "neo4j",
    "AI_GOVERNANCE_GRAPH_PASSWORD": "ai-governance-local-password",

    # Repository Configuration (all use inmemory for tests)
    "AI_GOVERNANCE_TENANCY_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_SETTINGS_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_POLICY_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_EVALUATION_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_EXPERIMENT_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_EXPERIMENT_CANDIDATE_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_EVALUATION_RUN_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_LEADERBOARD_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_PROMPT_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_MODEL_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_DATASET_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_JOB_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_GOVERNANCE_DECISION_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_REPOSITORY": "inmemory",
    "AI_GOVERNANCE_ONTOLOGY_REPOSITORY": "inmemory",

    # MCP Configuration
    "AI_GOVERNANCE_MCP_DRY_RUN_DEFAULT": "False",

    # Extras
    "MODEL_REGISTRY_URL": "http://127.0.0.1:1234/",
}

# Only set if not already set in the environment
for key, value in _defaults.items():
    if key not in os.environ:
        os.environ[key] = value

# Clear any SQLite paths that might have been set (they're not needed for inmemory)
for key in list(os.environ.keys()):
    if key.endswith("_SQLITE_PATH"):
        del os.environ[key]


def pytest_collection_modifyitems(config, items):
    """Skip external-provider tests when their credentials are unavailable."""
    if os.getenv("OPENAI_API_KEY"):
        return
    skip = pytest.mark.skip(reason="OPENAI_API_KEY is not configured")
    for item in items:
        if item.nodeid == "tests/integration/test_trulens_provider.py::test_answer_relevance":
            item.add_marker(skip)
