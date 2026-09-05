"""Versioned runtime settings for deterministic causal-audit methodology v1."""

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
    range_validator,
)

CAUSAL_AUDIT_DEFINITIONS = (
    _definition(
        "causal_audit.influence_threshold",
        C.AGENTS_RUNTIME,
        "Causal Audit — Influence Threshold",
        "Minimum outcome-score change considered material for causal-audit/v1. Default 0.01 follows the supplied research methodology and is not a universal scientific constant.",
        T.FLOAT,
        0.01,
        env="AI_GOVERNANCE_CAUSAL_AUDIT_INFLUENCE_THRESHOLD",
        runtime_applied=True,
        validator=range_validator(0.0, 1_000_000.0),
    ),
    _definition(
        "causal_audit.saturation_threshold",
        C.AGENTS_RUNTIME,
        "Causal Audit — Saturation Threshold",
        "Outcome-score level at which later tool calls are classified as post-saturation in causal-audit/v1. Default 0.95 is methodology-specific.",
        T.FLOAT,
        0.95,
        env="AI_GOVERNANCE_CAUSAL_AUDIT_SATURATION_THRESHOLD",
        runtime_applied=True,
        validator=range_validator(0.0, 1_000_000.0),
    ),
    _definition(
        "causal_audit.default_counterfactual_samples",
        C.AGENTS_RUNTIME,
        "Causal Audit — Default Counterfactual Samples",
        "Default number of isolated counterfactual outcomes requested for each tool call.",
        T.INTEGER,
        3,
        env="AI_GOVERNANCE_CAUSAL_AUDIT_DEFAULT_COUNTERFACTUAL_SAMPLES",
        runtime_applied=True,
        validator=range_validator(1, 100),
    ),
    _definition(
        "causal_audit.max_counterfactual_samples",
        C.AGENTS_RUNTIME,
        "Causal Audit — Maximum Counterfactual Samples",
        "Upper bound for a causal-audit request to preserve predictable worker load.",
        T.INTEGER,
        10,
        env="AI_GOVERNANCE_CAUSAL_AUDIT_MAX_COUNTERFACTUAL_SAMPLES",
        runtime_applied=True,
        validator=range_validator(1, 100),
    ),
    _definition(
        "causal_audit.max_tool_calls",
        C.AGENTS_RUNTIME,
        "Causal Audit — Maximum Tool Calls",
        "Maximum auditable tool calls in one execution; larger trajectories fail closed.",
        T.INTEGER,
        20,
        env="AI_GOVERNANCE_CAUSAL_AUDIT_MAX_TOOL_CALLS",
        runtime_applied=True,
        validator=range_validator(1, 1000),
    ),
)
