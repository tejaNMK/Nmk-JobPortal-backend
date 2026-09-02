import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.jobs.job_alert_digest_scheduler import (
    JOB_ALERT_DUE_DIGEST_JOB_ID,
    JobAlertDigestScheduler,
    _load_timezone,
    shutdown_job_alert_digest_scheduler,
    start_job_alert_digest_scheduler,
)


def test_load_timezone_accepts_iana_name():
    timezone = _load_timezone("America/New_York")

    assert timezone is not None


def test_load_timezone_rejects_fixed_offset():
    try:
        _load_timezone("+05:30")
    except Exception as exc:
        assert "time zone" in str(exc).lower()
    else:
        raise AssertionError("fixed offset timezone should be rejected")


def test_scheduler_registers_single_utc_interval_task(monkeypatch):
    created_tasks = []

    def fake_create_task(coro, name):
        coro.close()
        task = SimpleNamespace(name=name, cancel=lambda: None)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    scheduler = JobAlertDigestScheduler(
        db_engine=SimpleNamespace(),
        interval_minutes=15,
        sleep=AsyncMock(),
    )

    scheduler.start()
    scheduler.start()

    assert [task.name for task in created_tasks] == [JOB_ALERT_DUE_DIGEST_JOB_ID]
    assert scheduler.interval_seconds == 900


def test_start_job_alert_digest_scheduler_prevents_duplicate_registration(monkeypatch):
    started = []

    class FakeScheduler:
        def start(self):
            started.append(True)

    monkeypatch.setattr(
        "app.jobs.job_alert_digest_scheduler.JOB_ALERT_SCHEDULER_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.jobs.job_alert_digest_scheduler.JobAlertDigestScheduler",
        FakeScheduler,
    )
    app = SimpleNamespace(state=SimpleNamespace())

    start_job_alert_digest_scheduler(app)
    start_job_alert_digest_scheduler(app)

    assert len(started) == 1


def test_start_job_alert_digest_scheduler_respects_disabled_config(monkeypatch):
    monkeypatch.setattr(
        "app.jobs.job_alert_digest_scheduler.JOB_ALERT_SCHEDULER_ENABLED",
        False,
    )
    app = SimpleNamespace(state=SimpleNamespace())

    start_job_alert_digest_scheduler(app)

    assert not hasattr(app.state, "job_alert_digest_scheduler")


def test_shutdown_job_alert_digest_scheduler_stops_registered_scheduler():
    scheduler = SimpleNamespace(shutdown=AsyncMock(return_value=None))
    app = SimpleNamespace(state=SimpleNamespace(job_alert_digest_scheduler=scheduler))

    asyncio.run(shutdown_job_alert_digest_scheduler(app))

    scheduler.shutdown.assert_awaited_once()
    assert app.state.job_alert_digest_scheduler is None
