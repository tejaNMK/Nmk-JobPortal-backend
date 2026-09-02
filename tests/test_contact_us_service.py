from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.schema.contact_us_schema import ContactUsCreateSchema, ContactUsResponseSchema
from app.service.contact_us_service import ContactUsService


class _TurnstileResponse:
    def __init__(self, payload, *, status_code: int = 200, json_error: Exception | None = None):
        self._payload = payload
        self.status_code = status_code
        self._json_error = json_error
        self.request = httpx.Request("POST", "https://turnstile.example/siteverify")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "upstream error",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


class _TurnstileClient:
    def __init__(self, response=None, *, exception: Exception | None = None):
        self.response = response
        self.exception = exception
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, data):
        self.post_calls.append((url, data))
        if self.exception:
            raise self.exception
        return self.response


def _patch_turnstile_client(monkeypatch, client: _TurnstileClient):
    monkeypatch.setattr(
        "app.service.contact_us_service.httpx.AsyncClient",
        lambda *args, **kwargs: client,
    )


def test_build_response_classmethod_accepts_inquiry():
    inquiry = SimpleNamespace(
        inquiry_id="inquiry-1",
        email_status=ContactUsService.EMAIL_STATUS_SENT,
    )

    response = ContactUsService._build_response(inquiry)

    assert isinstance(response, ContactUsResponseSchema)
    assert response.inquiry_id == "inquiry-1"
    assert response.email_status == ContactUsService.EMAIL_STATUS_SENT


@pytest.mark.asyncio
async def test_submit_contact_inquiry_builds_response_after_email_processing(monkeypatch):
    request = ContactUsCreateSchema(
        full_name="Jane Doe",
        email="jane@example.com",
        phone_number="9876543210",
        inquiry_type="TECHNICAL_ISSUE",
        custom_subject=None,
        message="I cannot apply to a job from the portal.",
        turnstile_token="turnstile-token",
    )
    saved_inquiry = SimpleNamespace(
        inquiry_id="inquiry-2",
        email_status=ContactUsService.EMAIL_STATUS_FAILED,
    )

    verify_turnstile = AsyncMock(return_value=None)
    build_inquiry = staticmethod(lambda request: saved_inquiry)
    save_inquiry = AsyncMock(return_value=saved_inquiry)
    process_email_delivery = AsyncMock(return_value=None)
    monkeypatch.setattr(ContactUsService, "verify_turnstile", verify_turnstile)
    monkeypatch.setattr(ContactUsService, "_build_inquiry", build_inquiry)
    monkeypatch.setattr(ContactUsService, "_save_inquiry", save_inquiry)
    monkeypatch.setattr(
        ContactUsService,
        "_process_email_delivery",
        process_email_delivery,
    )

    response = await ContactUsService.submit_contact_inquiry(
        session=None,
        request=request,
    )

    assert isinstance(response, ContactUsResponseSchema)
    assert response.inquiry_id == "inquiry-2"
    assert response.email_status == ContactUsService.EMAIL_STATUS_FAILED
    verify_turnstile.assert_awaited_once_with("turnstile-token")
    save_inquiry.assert_awaited_once()
    process_email_delivery.assert_awaited_once_with(
        session=None,
        inquiry=saved_inquiry,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("secret", [None, "", "   "])
async def test_verify_turnstile_missing_secret_fails_closed(monkeypatch, secret):
    monkeypatch.setattr("app.service.contact_us_service.TURNSTILE_SECRET_KEY", secret)

    with pytest.raises(HTTPException) as exc_info:
        await ContactUsService.verify_turnstile("client-token")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "CAPTCHA verification service is unavailable."


@pytest.mark.asyncio
async def test_verify_turnstile_success_posts_secret_and_token(monkeypatch):
    monkeypatch.setattr("app.service.contact_us_service.TURNSTILE_SECRET_KEY", "server-secret")
    client = _TurnstileClient(_TurnstileResponse({"success": True}))
    _patch_turnstile_client(monkeypatch, client)

    await ContactUsService.verify_turnstile("client-token")

    assert client.post_calls == [
        (
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            {"secret": "server-secret", "response": "client-token"},
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"success": False},
        {"success": False, "error-codes": ["invalid-input-response"]},
        {"success": False, "error-codes": ["timeout-or-duplicate"]},
        {"success": False, "error-codes": ["invalid-input-secret"]},
    ],
)
async def test_verify_turnstile_invalid_captcha_is_client_validation_error(monkeypatch, payload):
    monkeypatch.setattr("app.service.contact_us_service.TURNSTILE_SECRET_KEY", "server-secret")
    _patch_turnstile_client(monkeypatch, _TurnstileClient(_TurnstileResponse(payload)))

    with pytest.raises(ValueError, match="Captcha validation failed"):
        await ContactUsService.verify_turnstile("client-token")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception",
    [
        httpx.TimeoutException("timeout"),
        httpx.ConnectError("connect failed"),
    ],
)
async def test_verify_turnstile_upstream_request_failure_is_503(monkeypatch, exception):
    monkeypatch.setattr("app.service.contact_us_service.TURNSTILE_SECRET_KEY", "server-secret")
    _patch_turnstile_client(monkeypatch, _TurnstileClient(exception=exception))

    with pytest.raises(HTTPException) as exc_info:
        await ContactUsService.verify_turnstile("client-token")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "CAPTCHA verification service is unavailable."


@pytest.mark.asyncio
async def test_verify_turnstile_upstream_http_failure_is_503(monkeypatch):
    monkeypatch.setattr("app.service.contact_us_service.TURNSTILE_SECRET_KEY", "server-secret")
    _patch_turnstile_client(
        monkeypatch,
        _TurnstileClient(_TurnstileResponse({"error": "bad gateway"}, status_code=502)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await ContactUsService.verify_turnstile("client-token")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _TurnstileResponse(None, json_error=ValueError("not json")),
        _TurnstileResponse(["not", "an", "object"]),
    ],
)
async def test_verify_turnstile_unusable_upstream_response_is_503(monkeypatch, response):
    monkeypatch.setattr("app.service.contact_us_service.TURNSTILE_SECRET_KEY", "server-secret")
    _patch_turnstile_client(monkeypatch, _TurnstileClient(response))

    with pytest.raises(HTTPException) as exc_info:
        await ContactUsService.verify_turnstile("client-token")

    assert exc_info.value.status_code == 503


@pytest.mark.parametrize("token", ["", "   "])
def test_contact_us_schema_rejects_empty_turnstile_token(token):
    with pytest.raises(ValueError, match="Captcha validation token is required"):
        ContactUsCreateSchema(
            full_name="Jane Doe",
            email="jane@example.com",
            phone_number="9876543210",
            inquiry_type="TECHNICAL_ISSUE",
            custom_subject=None,
            message="I cannot apply to a job from the portal.",
            turnstile_token=token,
        )


@pytest.mark.asyncio
async def test_submit_contact_inquiry_does_not_save_when_turnstile_unavailable(monkeypatch):
    request = ContactUsCreateSchema(
        full_name="Jane Doe",
        email="jane@example.com",
        phone_number="9876543210",
        inquiry_type="TECHNICAL_ISSUE",
        custom_subject=None,
        message="I cannot apply to a job from the portal.",
        turnstile_token="turnstile-token",
    )
    verify_turnstile = AsyncMock(
        side_effect=HTTPException(
            status_code=503,
            detail="CAPTCHA verification service is unavailable.",
        )
    )
    save_inquiry = AsyncMock()
    process_email_delivery = AsyncMock()
    monkeypatch.setattr(ContactUsService, "verify_turnstile", verify_turnstile)
    monkeypatch.setattr(ContactUsService, "_save_inquiry", save_inquiry)
    monkeypatch.setattr(ContactUsService, "_process_email_delivery", process_email_delivery)

    with pytest.raises(HTTPException) as exc_info:
        await ContactUsService.submit_contact_inquiry(session=None, request=request)

    assert exc_info.value.status_code == 503
    save_inquiry.assert_not_awaited()
    process_email_delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_contact_inquiry_does_not_save_when_turnstile_invalid(monkeypatch):
    request = ContactUsCreateSchema(
        full_name="Jane Doe",
        email="jane@example.com",
        phone_number="9876543210",
        inquiry_type="TECHNICAL_ISSUE",
        custom_subject=None,
        message="I cannot apply to a job from the portal.",
        turnstile_token="turnstile-token",
    )
    verify_turnstile = AsyncMock(side_effect=ValueError("Captcha validation failed."))
    save_inquiry = AsyncMock()
    process_email_delivery = AsyncMock()
    monkeypatch.setattr(ContactUsService, "verify_turnstile", verify_turnstile)
    monkeypatch.setattr(ContactUsService, "_save_inquiry", save_inquiry)
    monkeypatch.setattr(ContactUsService, "_process_email_delivery", process_email_delivery)

    with pytest.raises(ValueError, match="Captcha validation failed"):
        await ContactUsService.submit_contact_inquiry(session=None, request=request)

    save_inquiry.assert_not_awaited()
    process_email_delivery.assert_not_awaited()
