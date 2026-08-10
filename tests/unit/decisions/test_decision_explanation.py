from ai_governance.decisions import (
    DecisionEvidenceReference,
    DecisionExplanation,
    DecisionPolicyReference,
    MissingEvidence,
)


def test_decision_explanation_is_deterministic_container() -> None:
    explanation = DecisionExplanation(
        decision_id="decision-1",
        summary="Candidate candidate-1 was blocked because policy failed.",
        reasons=("policy failed",),
        evidence_references=(
            DecisionEvidenceReference(
                evidence_type="Metric",
                evidence_id="metric-1",
            ),
        ),
        policy_references=(
            DecisionPolicyReference(
                policy_id="policy-1",
                policy_version="1",
                policy_name="quality gate",
            ),
        ),
        missing_evidence=(
            MissingEvidence(
                evidence_type="Target",
                reason="Target entity was not found.",
                severity="CRITICAL",
            ),
        ),
        metadata={"source": "unit-test"},
    )

    assert explanation.reasons == ("policy failed",)
    assert explanation.evidence_references[0].evidence_id == "metric-1"
    assert explanation.policy_references[0].policy_name == "quality gate"
    assert explanation.missing_evidence[0].severity == "CRITICAL"
    assert explanation.metadata == {"source": "unit-test"}
