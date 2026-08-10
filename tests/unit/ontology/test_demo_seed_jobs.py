from ai_governance.domain.jobs import JobStatus
from ai_governance.ontology.demo_seed import seed_demo_jobs
from ai_governance.repositories.in_memory import InMemoryJobRepository


def test_demo_job_seed_does_not_leave_legacy_fixture_jobs_active() -> None:
    repository = InMemoryJobRepository()

    seed_demo_jobs(repository)

    jobs = {job.job_id: job for job in repository.list_jobs()}
    for job_id in (
        "job-demo-eval-review",
        "job-demo-experiment-candidate-sweep",
        "job-demo-replay-release-gate",
        "job-demo-drift-nightly",
    ):
        assert jobs[job_id].status is JobStatus.SUCCEEDED
        assert jobs[job_id].result_ref is not None

    assert not [
        job
        for job in jobs.values()
        if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}
    ]
