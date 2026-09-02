from datetime import datetime, timedelta, timezone

from jose import jwt

from app import config
from app.model.authentication.mapper_bootstrap import bootstrap_mappers
from app.model.contact_us_model import ContactUsInquiry
from app.model.notification import Notification
from app.repository.authentication import auth_repo
from app.repository.authentication.auth_repo import JWTRepo
from app.utils.utc import utc_now, utc_now_naive


bootstrap_mappers()


def test_utc_now_is_timezone_aware_utc():
    value = utc_now()

    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(0)


def test_utc_now_naive_preserves_naive_utc_db_contract():
    value = utc_now_naive()

    assert value.tzinfo is None
    assert abs((datetime.now(timezone.utc).replace(tzinfo=None) - value).total_seconds()) < 2


def test_timezone_aware_model_defaults_are_aware_and_fresh():
    first = ContactUsInquiry(
        full_name="NMK User",
        email="user@example.com",
        inquiry_type="GENERAL",
        message="Please contact me about the portal.",
    )
    second = ContactUsInquiry(
        full_name="NMK User",
        email="second@example.com",
        inquiry_type="GENERAL",
        message="Please contact me about the portal.",
    )

    assert first.created_at.tzinfo is not None
    assert first.created_at.utcoffset() == timedelta(0)
    assert second.created_at >= first.created_at


def test_naive_db_model_defaults_remain_naive_utc():
    notification = Notification(
        notification_id="notif-1",
        recipient_id="recipient-1",
        title="Title",
        message="Message",
        notification_type="SYSTEM",
    )

    assert notification.created_at.tzinfo is None
    assert notification.updated_at.tzinfo is None


def test_jwt_expiry_uses_aware_utc_without_changing_duration(monkeypatch):
    fixed_now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    secret = "test-only-secure-jwt-secret-for-aware-exp-claim-64-bytes"
    monkeypatch.setattr(auth_repo, "JWT_SECRET_KEY", secret)
    monkeypatch.setattr(auth_repo, "utc_now", lambda: fixed_now)

    token = JWTRepo(data={"user_id": "user-1"}).generate_token(
        expires_delta=timedelta(minutes=5)
    )
    payload = jwt.decode(token, secret, algorithms=[config.ALGORITHM])

    assert payload["exp"] == int((fixed_now + timedelta(minutes=5)).timestamp())
