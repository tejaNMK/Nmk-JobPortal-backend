import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schema.email_verification import SendOtpSchema


class _ClientError(Exception):
    pass


boto3_stub = types.ModuleType("boto3")
boto3_stub.client = MagicMock()
botocore_stub = types.ModuleType("botocore")
botocore_exceptions_stub = types.ModuleType("botocore.exceptions")
botocore_exceptions_stub.ClientError = _ClientError
sys.modules.setdefault("boto3", boto3_stub)
sys.modules.setdefault("botocore", botocore_stub)
sys.modules.setdefault("botocore.exceptions", botocore_exceptions_stub)

from app.service.authentication.auth_service import AuthService


@pytest.mark.asyncio
async def test_send_otp_rejects_already_registered_email():
    existing_user = MagicMock()
    existing_user.email = "john.doe@example.com"
    request = SendOtpSchema(email="John.Doe@Example.com")

    with patch(
        "app.service.authentication.auth_service.UsersRepository.find_by_email",
        new_callable=AsyncMock,
        return_value=existing_user,
    ) as find_by_email, patch(
        "app.service.authentication.auth_service.EmailVerificationTokenRepository.get_last_send_time",
        new_callable=AsyncMock,
    ) as get_last_send_time, patch(
        "app.service.authentication.auth_service.EmailService.send_email_verification_otp_email",
        new_callable=AsyncMock,
    ) as send_email:
        with pytest.raises(HTTPException) as exc_info:
            await AuthService.send_otp_service(session=MagicMock(), request_body=request)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Email is already taken."
    find_by_email.assert_awaited_once()
    assert find_by_email.await_args.args[1] == "john.doe@example.com"
    get_last_send_time.assert_not_awaited()
    send_email.assert_not_awaited()
