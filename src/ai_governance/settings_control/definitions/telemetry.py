from __future__ import annotations

from ai_governance.settings_control.domain import SettingScope

from .common import (
    Category as C,
)
from .common import (
    ValueType as T,
)
from .common import (
    definition as _definition,
)
from .common import (
    https_url as _https_url,
)
from .common import (
    optional_env_secret_reference as _optional_env_secret_reference,
)

TELEMETRY_DEFINITIONS = (
    _definition(
        "telemetry.mode",
        C.OBSERVABILITY,
        "Telemetry Mode",
        "Set to disabled to prevent all outbound product telemetry.",
        T.ENUM,
        "standard",
        env="AI_GOVERNANCE_TELEMETRY_MODE",
        enum=("standard", "disabled"),
        scopes=(SettingScope.SYSTEM,),
        runtime_applied=True,
    ),
    _definition(
        "telemetry.essential.enabled",
        C.OBSERVABILITY,
        "Essential Telemetry",
        "Anonymous installation compatibility telemetry. Disabled when telemetry mode is disabled.",
        T.BOOLEAN,
        True,
        env="AI_GOVERNANCE_TELEMETRY_ESSENTIAL_ENABLED",
        scopes=(SettingScope.SYSTEM,),
        runtime_applied=True,
    ),
    _definition(
        "telemetry.product_analytics.enabled",
        C.OBSERVABILITY,
        "Product Analytics",
        "Aggregated product adoption and workload counts. No customer content is sent.",
        T.BOOLEAN,
        False,
        env="AI_GOVERNANCE_TELEMETRY_PRODUCT_ANALYTICS_ENABLED",
        scopes=(SettingScope.SYSTEM,),
        runtime_applied=True,
    ),
    _definition(
        "telemetry.performance_research.enabled",
        C.OBSERVABILITY,
        "Performance Research",
        "Aggregated duration distributions. No traces, URLs, or request data are sent.",
        T.BOOLEAN,
        False,
        env="AI_GOVERNANCE_TELEMETRY_PERFORMANCE_RESEARCH_ENABLED",
        scopes=(SettingScope.SYSTEM,),
        runtime_applied=True,
    ),
    _definition(
        "telemetry.exporter.type",
        C.OBSERVABILITY,
        "Telemetry Exporter",
        "Outbound exporter. None performs no outbound telemetry I/O.",
        T.ENUM,
        "none",
        env="AI_GOVERNANCE_TELEMETRY_EXPORTER",
        enum=("none", "posthog"),
        scopes=(SettingScope.SYSTEM,),
        runtime_applied=True,
    ),
    _definition(
        "telemetry.exporter.posthog_api_key_ref",
        C.OBSERVABILITY,
        "PostHog API Key Reference",
        "Secret reference for a PostHog API key, for example env://POSTHOG_API_KEY.",
        T.STRING,
        "",
        env="AI_GOVERNANCE_TELEMETRY_POSTHOG_API_KEY_REF",
        validator=_optional_env_secret_reference,
        scopes=(SettingScope.SYSTEM,),
        runtime_applied=True,
    ),
    _definition(
        "telemetry.exporter.posthog_endpoint",
        C.OBSERVABILITY,
        "PostHog Endpoint",
        "HTTPS capture endpoint used only by the PostHog exporter.",
        T.STRING,
        "https://us.i.posthog.com/capture/",
        env="AI_GOVERNANCE_TELEMETRY_POSTHOG_ENDPOINT",
        validator=_https_url,
        scopes=(SettingScope.SYSTEM,),
        runtime_applied=True,
    ),
    _definition(
        "telemetry.aggregation_period",
        C.OBSERVABILITY,
        "Telemetry Aggregation Period",
        "Local aggregation period before an export snapshot is created.",
        T.DURATION,
        "1d",
        env="AI_GOVERNANCE_TELEMETRY_AGGREGATION_PERIOD",
        scopes=(SettingScope.SYSTEM,),
        runtime_applied=True,
    ),
)
