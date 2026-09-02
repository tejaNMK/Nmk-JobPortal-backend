from datetime import datetime, timezone
import importlib.util
from pathlib import Path

from sqlalchemy import DateTime, select

from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.model.employer_model.employer_profile import EmployerProfile
from app.model.employer_model.job_metrics import JobMetrics
from app.model.employer_model.shortlisted_candidate import ShortlistedCandidate


bootstrap_mappers()


def _load_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20260812_fix_text_timestamp_columns.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_20260812_fix_text_timestamp_columns",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_affected_models_use_timezone_aware_datetime_columns():
    columns = [
        EmployerProfile.__table__.c.created_at,
        EmployerProfile.__table__.c.updated_at,
        EmployerProfile.__table__.c.deleted_at,
        JobMetrics.__table__.c.last_viewed_at,
        JobMetrics.__table__.c.updated_at,
        ShortlistedCandidate.__table__.c.shortlisted_at,
    ]

    for column in columns:
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is True


def test_employer_profile_defaults_are_aware_utc_datetimes():
    profile = EmployerProfile(
        id="emp-1",
        user_id="00000000-0000-0000-0000-000000000001",
        company_name="NMK",
    )

    assert profile.created_at.tzinfo is not None
    assert profile.created_at.utcoffset().total_seconds() == 0
    assert profile.updated_at.tzinfo is not None
    assert profile.updated_at.utcoffset().total_seconds() == 0


def test_migration_converts_exact_affected_columns_only():
    migration = _load_migration_module()

    assert migration.revision == "20260812_fix_text_timestamp_columns"
    assert migration.down_revision == "20260812_applicant_ranking_cache"
    assert migration.TIMESTAMP_COLUMNS == (
        ("employer_profiles", "created_at", False, True),
        ("employer_profiles", "updated_at", False, True),
        ("employer_profiles", "deleted_at", True, False),
        ("job_metrics", "last_viewed_at", True, False),
        ("job_metrics", "updated_at", True, True),
        ("shortlisted_candidates", "shortlisted_at", True, True),
    )


def test_migration_uses_null_safe_timestamptz_conversion():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20260812_fix_text_timestamp_columns.py"
    )
    source = migration_path.read_text()

    assert "NULLIF(BTRIM({column_name}), '')::timestamptz" in source
    assert "Cannot convert %.% to timestamptz" in source
    assert "NOW()" not in source


def test_timestamp_queries_compile_as_native_datetime_comparisons():
    cutoff = datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)

    metrics_sql = str(
        select(JobMetrics)
        .where(JobMetrics.last_viewed_at >= cutoff)
        .order_by(JobMetrics.last_viewed_at.desc())
        .compile(compile_kwargs={"literal_binds": True})
    )
    shortlist_sql = str(
        select(ShortlistedCandidate)
        .where(ShortlistedCandidate.shortlisted_at >= cutoff)
        .order_by(ShortlistedCandidate.shortlisted_at.desc())
        .compile(compile_kwargs={"literal_binds": True})
    )

    assert "job_metrics.last_viewed_at >=" in metrics_sql
    assert "ORDER BY job_metrics.last_viewed_at DESC" in metrics_sql
    assert "shortlisted_candidates.shortlisted_at >=" in shortlist_sql
    assert "ORDER BY shortlisted_candidates.shortlisted_at DESC" in shortlist_sql
