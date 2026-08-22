from types import SimpleNamespace

from ai_governance.intelligence import ExperimentAdvisor
from ai_governance.intelligence.registry import (
    AdvisorRegistrationError,
    AdvisorRegistry,
    IntelligenceService,
)
from ai_governance.spi.intelligence import (
    AdvisorDescriptor,
    AdvisorEvidence,
    AdvisorFinding,
    AdvisorRequest,
    AdvisorSelection,
    FindingSeverity,
    ReasoningPlan,
)


class StubAdvisor:
    descriptor = AdvisorDescriptor("stub", "1", "Stub", ("test",))

    def analyze(self, request: AdvisorRequest) -> AdvisorFinding:
        return AdvisorFinding(
            advisor_id="stub",
            advisor_version="1",
            severity=FindingSeverity.INFO,
            summary=f"Evidence for {request.question}",
            findings=(AdvisorEvidence("stub:1", "test", "Stub evidence"),),
        )


class StubPlanner:
    planner_id = "stub-planner"
    version = "1"

    def plan(self, request, advisors):
        assert [advisor.advisor_id for advisor in advisors] == ["stub"]
        return ReasoningPlan(
            planner_id=self.planner_id,
            planner_version=self.version,
            selected_advisor_ids=("stub",),
            selections=(AdvisorSelection("stub", True, "test selection"),),
        )


def test_intelligence_service_plans_before_collecting_evidence() -> None:
    service = IntelligenceService(AdvisorRegistry((StubAdvisor(),)), StubPlanner())
    request = AdvisorRequest("What changed?", {"organization_id": "org-acme"})

    plan = service.plan(request)
    result = service.collect(request, plan)

    assert plan.as_dict()["selected_advisors"] == ["stub"]
    assert result.as_dict()["findings"] == [
        {
            "advisor": "stub",
            "advisor_version": "1",
            "status": "COMPLETED",
            "severity": "INFO",
            "summary": "Evidence for What changed?",
            "findings": [{"evidence_id": "stub:1", "kind": "test", "summary": "Stub evidence", "attributes": {}}],
            "metadata": {},
        }
    ]


def test_advisor_registry_rejects_ambiguous_advisor_ids() -> None:
    registry = AdvisorRegistry((StubAdvisor(),))

    try:
        registry.register(StubAdvisor())
    except AdvisorRegistrationError as error:
        assert str(error) == "Advisor 'stub' is already registered."
    else:  # pragma: no cover - keeps the assertion clear without pytest.raises
        raise AssertionError("Expected duplicate advisor registration to fail.")


def test_experiment_advisor_recommends_only_from_completed_ranking_evidence() -> None:
    ranking = SimpleNamespace(
        experiment_id="experiment-1",
        candidate=SimpleNamespace(candidate_id="candidate-a", name="Candidate A"),
        evaluation_run_id="run-1",
        evaluation_result_id="result-1",
        overall_score=0.91,
        rank=1,
        reason="Highest overall score.",
        ranking_strategy="overall_score",
    )

    class RankingSource:
        def rank_candidates(self, experiment_id: str):
            assert experiment_id == "experiment-1"
            return [ranking]

    finding = ExperimentAdvisor(RankingSource).analyze(
        AdvisorRequest(
            "Which candidate should win?",
            {"organization_id": "org-acme"},
            {"experiment_id": "experiment-1"},
        )
    )

    assert finding.metadata["recommended_candidate_id"] == "candidate-a"
    assert finding.findings[0].attributes["overall_score"] == 0.91
