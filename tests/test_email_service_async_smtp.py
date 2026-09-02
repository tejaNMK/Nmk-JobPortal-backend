import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosmtplib
import pytest

from app.constants.notification_constants import (
    NotificationChannel,
    NotificationFrequency,
)
from app.repository.job_alert_notification_delivery_repo import (
    JobAlertNotificationDeliveryRepo,
)
from app.service.authentication import email_service as email_service_module
from app.service.authentication.email_service import EmailService
from app.service.job_alert_notification_service import JobAlertNotificationService


def _set_smtp_env(monkeypatch, *, username="smtp-user", password="smtp-pass"):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "no-reply@example.test")
    monkeypatch.setenv("SMTP_REPLY_TO", "support@example.test")
    if username is None:
        monkeypatch.delenv("SMTP_USERNAME", raising=False)
    else:
        monkeypatch.setenv("SMTP_USERNAME", username)
    if password is None:
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("SMTP_PASSWORD", password)


def _install_fake_smtp(
    monkeypatch,
    *,
    starttls_exc=None,
    login_exc=None,
    send_exc=None,
    send_delay=0,
    events=None,
):
    instances = []

    class FakeSMTP:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = []
            self.login_args = None
            self.message = None
            instances.append(self)

        async def connect(self, **kwargs):
            self.calls.append(("connect", kwargs))

        async def starttls(self, **kwargs):
            self.calls.append(("starttls", kwargs))
            if starttls_exc:
                raise starttls_exc

        async def login(self, username, password, **kwargs):
            self.calls.append(("login", kwargs))
            self.login_args = (username, password)
            if login_exc:
                raise login_exc

        async def send_message(self, message, **kwargs):
            self.calls.append(("send_message", kwargs))
            self.message = message
            if send_delay:
                await asyncio.sleep(send_delay)
            if events is not None:
                events.append("send_message_done")
            if send_exc:
                raise send_exc

        async def quit(self):
            self.calls.append(("quit", {}))

    monkeypatch.setattr(email_service_module.aiosmtplib, "SMTP", FakeSMTP)
    return instances


@pytest.mark.asyncio
async def test_send_email_uses_async_aiosmtplib_and_preserves_message(monkeypatch):
    _set_smtp_env(monkeypatch)
    smtp_instances = _install_fake_smtp(monkeypatch)

    await EmailService._send_email(
        to_email="candidate@example.test",
        subject="Welcome",
        plain_body="Plain body",
        html_body="<p>HTML body</p>",
    )

    smtp = smtp_instances[0]
    assert smtp.kwargs == {
        "hostname": "smtp.example.test",
        "port": 587,
        "timeout": 15,
        "use_tls": False,
        "start_tls": False,
    }
    assert [call[0] for call in smtp.calls] == [
        "connect",
        "starttls",
        "login",
        "send_message",
        "quit",
    ]
    assert smtp.login_args == ("smtp-user", "smtp-pass")
    assert smtp.message["From"] == "no-reply@example.test"
    assert smtp.message["To"] == "candidate@example.test"
    assert smtp.message["Subject"] == "Welcome"
    assert smtp.message["Reply-To"] == "support@example.test"
    assert "Plain body" in smtp.message.get_body(("plain",)).get_content()
    assert "HTML body" in smtp.message.get_body(("html",)).get_content()


@pytest.mark.asyncio
async def test_send_email_skips_login_when_credentials_are_missing(monkeypatch):
    _set_smtp_env(monkeypatch, username=None, password=None)
    smtp_instances = _install_fake_smtp(monkeypatch)

    await EmailService._send_email(
        to_email="candidate@example.test",
        subject="No auth",
        plain_body="Plain",
        html_body="<p>HTML</p>",
    )

    assert "login" not in [call[0] for call in smtp_instances[0].calls]


@pytest.mark.asyncio
async def test_send_email_continues_when_starttls_is_unavailable(monkeypatch):
    _set_smtp_env(monkeypatch)
    smtp_instances = _install_fake_smtp(
        monkeypatch,
        starttls_exc=aiosmtplib.SMTPException("STARTTLS unavailable"),
    )

    await EmailService._send_email(
        to_email="candidate@example.test",
        subject="STARTTLS fallback",
        plain_body="Plain",
        html_body="<p>HTML</p>",
    )

    assert [call[0] for call in smtp_instances[0].calls] == [
        "connect",
        "starttls",
        "login",
        "send_message",
        "quit",
    ]


@pytest.mark.asyncio
async def test_send_email_propagates_auth_failure_and_quits(monkeypatch):
    _set_smtp_env(monkeypatch)
    smtp_instances = _install_fake_smtp(
        monkeypatch,
        login_exc=aiosmtplib.SMTPAuthenticationError(535, "auth failed"),
    )

    with pytest.raises(aiosmtplib.SMTPAuthenticationError):
        await EmailService._send_email(
            to_email="candidate@example.test",
            subject="Auth failure",
            plain_body="Plain",
            html_body="<p>HTML</p>",
        )

    assert [call[0] for call in smtp_instances[0].calls] == [
        "connect",
        "starttls",
        "login",
        "quit",
    ]


@pytest.mark.asyncio
async def test_send_email_propagates_send_failure_and_quits(monkeypatch):
    _set_smtp_env(monkeypatch)
    smtp_instances = _install_fake_smtp(
        monkeypatch,
        send_exc=aiosmtplib.SMTPException("send failed"),
    )

    with pytest.raises(aiosmtplib.SMTPException):
        await EmailService._send_email(
            to_email="candidate@example.test",
            subject="Send failure",
            plain_body="Plain",
            html_body="<p>HTML</p>",
        )

    assert [call[0] for call in smtp_instances[0].calls] == [
        "connect",
        "starttls",
        "login",
        "send_message",
        "quit",
    ]


@pytest.mark.asyncio
async def test_send_email_preserves_attachments(monkeypatch):
    _set_smtp_env(monkeypatch)
    smtp_instances = _install_fake_smtp(monkeypatch)

    await EmailService._send_email(
        to_email="candidate@example.test",
        subject="Attachment",
        plain_body="Plain",
        html_body="<p>HTML</p>",
        attachments=[("resume.txt", b"hello", "text/plain")],
    )

    attachments = list(smtp_instances[0].message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "resume.txt"
    assert attachments[0].get_content_type() == "text/plain"
    assert attachments[0].get_payload(decode=True) == b"hello"


@pytest.mark.asyncio
async def test_interview_email_preserves_calendar_attachment(monkeypatch):
    _set_smtp_env(monkeypatch)
    smtp_instances = _install_fake_smtp(monkeypatch)

    await EmailService.send_interview_scheduled_email(
        to_email="candidate@example.test",
        candidate_name="Jane Doe",
        interview_title="Technical Interview",
        company_name="Acme Corp",
        employer_name="Acme Hiring",
        job_title="Python Developer",
        interview_round="Technical",
        interview_date="2026-08-12",
        interview_time="10:00 AM",
        start_time="10:00 AM",
        end_time="10:30 AM",
        timezone="Asia/Kolkata",
        mode="ONLINE",
        meeting_link_or_location="https://meet.example.test/interview",
        interviewer="Alex",
        remarks="Bring portfolio",
        attachments=[
            (
                "interview-invite.ics",
                b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
                "text/calendar",
            )
        ],
    )

    attachments = list(smtp_instances[0].message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "interview-invite.ics"
    assert attachments[0].get_content_type() == "text/calendar"
    assert attachments[0].get_payload(decode=True) == b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"


@pytest.mark.asyncio
async def test_otp_wrappers_await_shared_async_sender(monkeypatch):
    send_email = AsyncMock(return_value=None)
    monkeypatch.setattr(EmailService, "_send_email", send_email)

    await EmailService.send_email_verification_otp_email(
        to_email="candidate@example.test",
        otp_code="123456",
        expires_in_minutes=10,
    )
    await EmailService.send_password_reset_otp_email(
        to_email="candidate@example.test",
        otp_code="654321",
        expires_in_minutes=5,
    )

    assert send_email.await_count == 2
    assert send_email.await_args_list[0].kwargs["subject"] == (
        "NMK Job Portal - Email Verification OTP"
    )
    assert send_email.await_args_list[1].kwargs["subject"] == (
        "NMK Job Portal - Password Reset OTP"
    )


@pytest.mark.asyncio
async def test_async_smtp_send_does_not_block_event_loop(monkeypatch):
    _set_smtp_env(monkeypatch)
    events = []
    _install_fake_smtp(monkeypatch, send_delay=0.05, events=events)

    async def probe():
        await asyncio.sleep(0.01)
        events.append("probe")

    send_task = asyncio.create_task(
        EmailService._send_email(
            to_email="candidate@example.test",
            subject="Nonblocking",
            plain_body="Plain",
            html_body="<p>HTML</p>",
        )
    )
    await asyncio.gather(send_task, probe())

    assert events == ["probe", "send_message_done"]


@pytest.mark.asyncio
async def test_instant_job_alert_email_marks_pending_delivery_sent(monkeypatch):
    alert = SimpleNamespace(
        alert_id="alert-1",
        candidate_id="candidate-1",
        user_id="user-1",
        email="candidate@example.test",
    )
    job = SimpleNamespace(
        job_id="job-1",
        title="Python Developer",
        company_name="Acme Corp",
        location="Hyderabad",
        employment_type="FULL_TIME",
        experience_min=2,
        experience_max=5,
        application_deadline=None,
    )
    reserve_delivery = AsyncMock(return_value=SimpleNamespace(id="delivery-1"))
    send_email = AsyncMock(return_value=None)
    mark_sent = AsyncMock(return_value=None)
    mark_failed = AsyncMock(return_value=None)
    monkeypatch.setattr(
        JobAlertNotificationDeliveryRepo,
        "reserve_delivery",
        reserve_delivery,
    )
    monkeypatch.setattr(EmailService, "send_job_alert_email", send_email)
    monkeypatch.setattr(JobAlertNotificationDeliveryRepo, "mark_sent", mark_sent)
    monkeypatch.setattr(JobAlertNotificationDeliveryRepo, "mark_failed", mark_failed)

    await JobAlertNotificationService._send_instant_email(
        session=None,
        alert=alert,
        job=job,
        candidate_name="Jane Doe",
    )

    reserve_delivery.assert_awaited_once()
    assert reserve_delivery.await_args.kwargs["frequency"] == NotificationFrequency.INSTANT
    assert reserve_delivery.await_args.kwargs["channel"] == NotificationChannel.EMAIL
    send_email.assert_awaited_once()
    mark_sent.assert_awaited_once_with(session=None, delivery_id="delivery-1")
    mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_instant_job_alert_email_marks_pending_delivery_failed(monkeypatch):
    alert = SimpleNamespace(
        alert_id="alert-1",
        candidate_id="candidate-1",
        user_id="user-1",
        email="candidate@example.test",
    )
    job = SimpleNamespace(
        job_id="job-1",
        title="Python Developer",
        company_name="Acme Corp",
        location="Hyderabad",
        employment_type="FULL_TIME",
        experience_min=2,
        experience_max=5,
        application_deadline=None,
    )
    reserve_delivery = AsyncMock(return_value=SimpleNamespace(id="delivery-1"))
    send_email = AsyncMock(side_effect=aiosmtplib.SMTPException("smtp password failed"))
    mark_sent = AsyncMock(return_value=None)
    mark_failed = AsyncMock(return_value=None)
    monkeypatch.setattr(
        JobAlertNotificationDeliveryRepo,
        "reserve_delivery",
        reserve_delivery,
    )
    monkeypatch.setattr(EmailService, "send_job_alert_email", send_email)
    monkeypatch.setattr(JobAlertNotificationDeliveryRepo, "mark_sent", mark_sent)
    monkeypatch.setattr(JobAlertNotificationDeliveryRepo, "mark_failed", mark_failed)

    await JobAlertNotificationService._send_instant_email(
        session=None,
        alert=alert,
        job=job,
        candidate_name="Jane Doe",
    )

    mark_sent.assert_not_awaited()
    mark_failed.assert_awaited_once()
    assert mark_failed.await_args.kwargs["delivery_id"] == "delivery-1"
    assert "password" not in mark_failed.await_args.kwargs["error"]


@pytest.mark.asyncio
async def test_digest_job_alert_email_marks_pending_delivery_sent(monkeypatch):
    alert = SimpleNamespace(
        alert_id="alert-1",
        candidate_id="candidate-1",
        email="candidate@example.test",
    )
    jobs = [SimpleNamespace(job_id="job-1", title="Python Developer")]
    reserve_delivery = AsyncMock(return_value=SimpleNamespace(id="digest-delivery"))
    send_summary_email = AsyncMock(return_value=None)
    mark_sent = AsyncMock(return_value=None)
    mark_failed = AsyncMock(return_value=None)
    monkeypatch.setattr(
        JobAlertNotificationDeliveryRepo,
        "reserve_delivery",
        reserve_delivery,
    )
    monkeypatch.setattr(EmailService, "send_job_alert_summary_email", send_summary_email)
    monkeypatch.setattr(JobAlertNotificationDeliveryRepo, "mark_sent", mark_sent)
    monkeypatch.setattr(JobAlertNotificationDeliveryRepo, "mark_failed", mark_failed)

    await JobAlertNotificationService._send_digest_email(
        session=None,
        alert=alert,
        jobs=jobs,
        candidate_name="Jane Doe",
        frequency=NotificationFrequency.DAILY,
        recipient_id="user-1",
        window_start=datetime(2026, 8, 10, 9, 0, 0),
        window_end=datetime(2026, 8, 11, 8, 59, 59),
    )

    reserve_delivery.assert_awaited_once()
    assert reserve_delivery.await_args.kwargs["frequency"] == NotificationFrequency.DAILY
    assert reserve_delivery.await_args.kwargs["channel"] == NotificationChannel.EMAIL
    send_summary_email.assert_awaited_once()
    mark_sent.assert_awaited_once_with(session=None, delivery_id="digest-delivery")
    mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_digest_job_alert_email_marks_pending_delivery_failed(monkeypatch):
    alert = SimpleNamespace(
        alert_id="alert-1",
        candidate_id="candidate-1",
        email="candidate@example.test",
    )
    jobs = [SimpleNamespace(job_id="job-1", title="Python Developer")]
    reserve_delivery = AsyncMock(return_value=SimpleNamespace(id="digest-delivery"))
    send_summary_email = AsyncMock(side_effect=aiosmtplib.SMTPException("smtp failed"))
    mark_sent = AsyncMock(return_value=None)
    mark_failed = AsyncMock(return_value=None)
    monkeypatch.setattr(
        JobAlertNotificationDeliveryRepo,
        "reserve_delivery",
        reserve_delivery,
    )
    monkeypatch.setattr(EmailService, "send_job_alert_summary_email", send_summary_email)
    monkeypatch.setattr(JobAlertNotificationDeliveryRepo, "mark_sent", mark_sent)
    monkeypatch.setattr(JobAlertNotificationDeliveryRepo, "mark_failed", mark_failed)

    await JobAlertNotificationService._send_digest_email(
        session=None,
        alert=alert,
        jobs=jobs,
        candidate_name="Jane Doe",
        frequency=NotificationFrequency.DAILY,
        recipient_id="user-1",
        window_start=datetime(2026, 8, 10, 9, 0, 0),
        window_end=datetime(2026, 8, 11, 8, 59, 59),
    )

    mark_sent.assert_not_awaited()
    mark_failed.assert_awaited_once()
    assert mark_failed.await_args.kwargs["delivery_id"] == "digest-delivery"
