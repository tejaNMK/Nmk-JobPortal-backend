import pytest

from fastapi import HTTPException
from unittest.mock import AsyncMock, patch

from app.service.authentication.auth_service import AuthService
from app.schema.auth import ForgotUserIdSchema


@pytest.mark.asyncio
async def test_forgot_userid_email_success():

    request = ForgotUserIdSchema(
        email="test@gmail.com"
    )

    mock_user = type(
        "User",
        (),
        {
            "user_id": "12345",
            "email": "test@gmail.com",
            "mobile_number": "9876543210",
            "country_code": "+91"
        }
    )()

    with patch(
        "app.service.authentication.auth_service.UsersRepository.find_by_email",
        new=AsyncMock(return_value=mock_user)
    ):

        with patch(
            "app.service.authentication.auth_service.SNSService.send_sms",
            new=AsyncMock()
        ):

            result = await AuthService.forgot_userid_service(
                None,
                request
            )

            assert (
                "If an account exists"
                in result["message"]
            )


@pytest.mark.asyncio
async def test_forgot_userid_user_not_found():

    request = ForgotUserIdSchema(
        email="nouser@gmail.com"
    )

    with patch(
        "app.service.authentication.auth_service.UsersRepository.find_by_email",
        new=AsyncMock(return_value=None)
    ):

        result = await AuthService.forgot_userid_service(
            None,
            request
        )

        assert (
            "If an account exists"
            in result["message"]
        )


@pytest.mark.asyncio
async def test_forgot_userid_email_failure():

    request = ForgotUserIdSchema(
        email="test@gmail.com"
    )

    mock_user = type(
        "User",
        (),
        {
            "user_id": "12345",
            "email": "test@gmail.com",
            "mobile_number": "9876543210",
            "country_code": "+91"
        }
    )()

    with patch(
        "app.service.authentication.auth_service.UsersRepository.find_by_email",
        new=AsyncMock(return_value=mock_user)
    ):

        with patch(
            "app.service.authentication.auth_service.SNSService.send_sms",
            new=AsyncMock(
                side_effect=Exception("SMS Down")
            )
        ):

            with pytest.raises(
                HTTPException
            ) as exc:

                await AuthService.forgot_userid_service(
                    session=None,
                    forgot_userid=request
                )

            assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_forgot_userid_mobile_lookup():

    request = ForgotUserIdSchema(
        mobile_number="9876543210"
    )

    mock_user = type(
        "User",
        (),
        {
            "user_id": "12345",
            "email": "test@gmail.com",
            "mobile_number": "9876543210",
            "country_code": "+91"
        }
    )()

    with patch(
        "app.service.authentication.auth_service.UsersRepository.find_by_mobile",
        new=AsyncMock(return_value=mock_user)
    ):

        with patch(
            "app.service.authentication.auth_service.SNSService.send_sms",
            new=AsyncMock()
        ):

            result = await AuthService.forgot_userid_service(
                None,
                request
            )

            assert (
                "registered mobile number"
                in result["message"]
            )


def test_forgot_userid_requires_contact():

    with pytest.raises(ValueError):

        ForgotUserIdSchema()


def test_forgot_userid_invalid_phone():

    with pytest.raises(ValueError):

        ForgotUserIdSchema(
            mobile_number="123"
        )


def test_forgot_userid_email_length():

    long_email = (
        "a" * 60
        + "@gmail.com"
    )

    with pytest.raises(ValueError):

        ForgotUserIdSchema(
            email=long_email
        )
