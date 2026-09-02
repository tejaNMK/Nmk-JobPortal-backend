from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from app.repository.candidate_repository.candidate_job_search_repo import CandidateJobSearchRepo


def test_candidate_search_active_predicate_excludes_closed_jobs():
    predicate = CandidateJobSearchRepo._active_job_predicate(datetime.now(UTC))
    compiled = str(
        predicate.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "jobs.status IN ('PUBLISHED')" in compiled
    assert "jobs.closed_at IS NULL" in compiled
    assert "jobs.is_deleted IS false" in compiled
