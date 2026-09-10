"""Provider-neutral identifiers for safe scaffold artifacts.

Scaffold implementations may retain their private working state, but the
evaluation domain records only stable, non-sensitive artifact identities.
"""

SCAFFOLD_PLAN_STORE_KEY = "ai_governance.scaffold.plan"
SCAFFOLD_PLAN_ARTIFACT_TYPE = "scaffold_plan"
SCAFFOLD_PLAN_SCHEMA_VERSION = "planner-executor-plan/v1"
