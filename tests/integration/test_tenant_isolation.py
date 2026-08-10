from __future__ import annotations

from datetime import UTC, datetime

from ai_governance.domain.jobs import JobExecutionContext, JobSubmission, JobType
from ai_governance.ontology import InMemoryOntologyGraphRepository, OntologyEntity
from ai_governance.repositories import InMemoryJobRepository
from ai_governance.services.job_submission_service import JobSubmissionService


def _submission(organization_id: str, project_id: str) -> JobSubmission:
    return JobSubmission(
        job_type=JobType.EVALUATION,
        input_refs={"execution_id": "same"},
        idempotency_key="same-key",
        submitted_by="actor",
        execution_context=JobExecutionContext(
            organization_id, project_id, "actor", "request", None
        ),
    )


def test_job_ids_lists_and_idempotency_are_tenant_isolated():
    repository = InMemoryJobRepository()
    ids = iter(("job_a", "job_b"))
    service = JobSubmissionService(repository, id_generator=lambda: next(ids))
    first = service.submit(_submission("org_a", "project_a"))
    second = service.submit(_submission("org_b", "project_b"))
    assert first.job_id != second.job_id
    assert repository.find_by_id("job_a", "org_b", "project_b") is None
    assert repository.list_jobs(organization_id="org_a", project_id="project_a") == [
        first
    ]
    assert repository.list_jobs(organization_id="org_b", project_id="project_b") == [
        second
    ]


def test_ontology_identifiers_are_isolated_by_tenant():
    repository = InMemoryOntologyGraphRepository()
    now = datetime.now(UTC)
    for organization_id, project_id, owner in (
        ("org_a", "project_a", "owner-a"),
        ("org_b", "project_b", "owner-b"),
    ):
        repository.save_entity(
            OntologyEntity(
                entity_id="same-id",
                entity_type="Actor",
                owner=owner,
                lifecycle="ACTIVE",
                created_at=now,
                organization_id=organization_id,
                project_id=project_id,
            )
        )
    assert (
        repository.get_entity("Actor", "same-id", "org_a", "project_a").owner
        == "owner-a"
    )
    assert (
        repository.get_entity("Actor", "same-id", "org_b", "project_b").owner
        == "owner-b"
    )
    assert repository.get_entity("Actor", "same-id", "org_a", "project_b") is None
