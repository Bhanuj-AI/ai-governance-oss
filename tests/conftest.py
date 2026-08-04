"""
Pytest configuration.

Sets default environment variables for all tests. This ensures tests run with
the same configuration as the local development environment without hardcoding
defaults in os.getenv() calls.

Overrides Docker-specific paths (like /var/lib/kavach) with local paths
for the test environment.
"""

from __future__ import annotations

import os

import pytest

# Set default environment variables for tests
_defaults = {
    # Kavach Configuration
    "KAVACH_ENV": "local",
    "KAVACH_CORS_ALLOW_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
    "KAVACH_AUTO_SEED_DEMO_DATA": "true",
    "KAVACH_API_LOG_LEVEL": "debug",
    "KAVACH_API_HOST": "localhost",
    "KAVACH_API_PORT": "8000",

    # IDP Configuration
    "KAVACH_AUTH_MODE": "development",
    "KAVACH_IDENTITY_PROVIDER": "development",
    "KAVACH_DEVELOPMENT_ACTOR_ID": "local-admin",
    "KAVACH_DEVELOPMENT_ACTOR_NAME": "Local Administrator",
    "KAVACH_OIDC_ISSUER": "http://localhost:8080/realms/kavach",
    "KAVACH_OIDC_JWKS_REFRESH_SECONDS": "300",

    # RBAC & Multi-Tenant Configuration
    "KAVACH_ALLOW_DEVELOPMENT_IDENTITY_IN_PRODUCTION": "false",
    "KAVACH_TENANCY_ENABLED": "true",

    # Bootstrap Configuration
    "KAVACH_BOOTSTRAP_ORGANIZATION_ID": "org_default",
    "KAVACH_BOOTSTRAP_ORGANIZATION_NAME": "Default Organization",
    "KAVACH_BOOTSTRAP_ORGANIZATION_SLUG": "default",
    "KAVACH_BOOTSTRAP_PROJECT_ID": "project_default",
    "KAVACH_BOOTSTRAP_PROJECT_NAME": "Default Project",
    "KAVACH_BOOTSTRAP_PROJECT_SLUG": "default",

    # Graph DB Configuration
    "KAVACH_GRAPH_URI": "bolt://neo4j:7687",
    "KAVACH_GRAPH_USER": "neo4j",
    "KAVACH_GRAPH_PASSWORD": "kavach-local-password",

    # Repository Configuration (all use inmemory for tests)
    "KAVACH_TENANCY_REPOSITORY": "inmemory",
    "KAVACH_SETTINGS_REPOSITORY": "inmemory",
    "KAVACH_POLICY_REPOSITORY": "inmemory",
    "KAVACH_EVALUATION_REPOSITORY": "inmemory",
    "KAVACH_EXPERIMENT_REPOSITORY": "inmemory",
    "KAVACH_EXPERIMENT_CANDIDATE_REPOSITORY": "inmemory",
    "KAVACH_EVALUATION_RUN_REPOSITORY": "inmemory",
    "KAVACH_LEADERBOARD_REPOSITORY": "inmemory",
    "KAVACH_PROMPT_REPOSITORY": "inmemory",
    "KAVACH_MODEL_REPOSITORY": "inmemory",
    "KAVACH_DATASET_REPOSITORY": "inmemory",
    "KAVACH_JOB_REPOSITORY": "inmemory",
    "KAVACH_GOVERNANCE_DECISION_REPOSITORY": "inmemory",
    "KAVACH_ONTOLOGY_SYNC_EVENT_REPOSITORY": "inmemory",
    "KAVACH_ONTOLOGY_REPOSITORY": "inmemory",

    # MCP Configuration
    "KAVACH_MCP_DRY_RUN_DEFAULT": "False",

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
