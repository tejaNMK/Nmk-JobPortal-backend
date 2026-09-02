"""Tests for forgot password endpoint"""

from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.model.authentication.users import Users
from app.repository.authentication.password_reset_token import PasswordResetTokenRepository
from app.repository.authentication.users import UsersRepository
from app.schema.auth import ForgotPasswordSchema, ResetPasswordSchema
from app.service.authentication.auth_service import AuthService


valid_forgot_password_data_email = {
    "email": "john.doe@example.com"
}


class TestForgotPasswordSchema:
    """Test ForgotPasswordSchema validation"""

    def test_valid_email(self):
        schema = ForgotPasswordSchema(**valid_forgot_password_data_email)
        assert schema.email == "john.doe@example.com"

    def test_missing_email(self):
        with pytest.raises(ValidationError, match="Either email or mobile number is required",):
            ForgotPasswordSchema()


class TestResetPasswordSchema:
    """Test ResetPasswordSchema validation"""

    def test_valid_reset_data(self):
        schema = ResetPasswordSchema(
            email="john.doe@example.com",
            otp_code="123456",
            new_password="SecurePass123!",
            confirm_password="SecurePass123!",
        )
        assert schema.email == "john.doe@example.com"
        assert schema.otp_code == "123456"
        assert schema.new_password == "SecurePass123!"

    def test_missing_otp_code(self):
        with pytest.raises(ValidationError):
            ResetPasswordSchema(
                email="john.doe@example.com",
                new_password="SecurePass123!",
                confirm_password="SecurePass123!",
            )

    def test_passwords_do_not_match(self):
        with pytest.raises(ValidationError, match="Passwords do not match"):
            ResetPasswordSchema(
                email="john.doe@example.com",
                otp_code="123456",
                new_password="SecurePass123!",
                confirm_password="DifferentPass123!",
            )

    def test_password_too_short(self):
        with pytest.raises(
            ValidationError,
            match="Password must be between 8 and 25 characters",
        ):
            ResetPasswordSchema(
                email="john.doe@example.com",
                otp_code="123456",
                new_password="short",
                confirm_password="short",
            )


class TestForgotPasswordService:
    """Forgot password endpoint/service no longer exists"""

    def test_placeholder(self):
        assert True


class TestResetPasswordService:
    """Test reset password service logic with mocked dependencies"""

    @patch("app.service.authentication.auth_service.UsersRepository")
    @patch("app.service.authentication.auth_service.PasswordResetTokenRepository")
    def test_reset_password_invalid_otp(
        self,
        mock_token_repo,
        mock_users_repo,
    ):
        mock_users_repo.find_by_email = AsyncMock(return_value=MagicMock(user_id=uuid4()))
        mock_token_repo.find_valid_otp_by_user_and_code = AsyncMock(return_value=None)

        from fastapi import HTTPException
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        with pytest.raises(HTTPException, match="Invalid or expired OTP code"):
            loop.run_until_complete(
                AuthService.reset_password_service(
                    ResetPasswordSchema(
                        email="john.doe@example.com",
                        otp_code="000000",
                        new_password="SecurePass123!",
                        confirm_password="SecurePass123!",
                    )
                )
            )

    @patch("app.service.authentication.auth_service.UsersRepository")
    @patch("app.service.authentication.auth_service.PasswordResetTokenRepository")
    def test_reset_password_user_not_found(self, mock_token_repo, mock_users_repo):
        mock_user_for_otp = MagicMock(user_id=uuid4())
        mock_token = MagicMock(token_id=uuid4(), user_id=mock_user_for_otp.user_id)

        mock_users_repo.find_by_email = AsyncMock(return_value=mock_user_for_otp)
        mock_token_repo.find_valid_otp_by_user_and_code = AsyncMock(return_value=mock_token)
        mock_users_repo.find_by_user_id = AsyncMock(return_value=None)

        from fastapi import HTTPException
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        with pytest.raises(HTTPException, match="User not found"):
            loop.run_until_complete(
                AuthService.reset_password_service(
                    ResetPasswordSchema(
                        email="john.doe@example.com",
                        otp_code="123456",
                        new_password="SecurePass123!",
                        confirm_password="SecurePass123!",
                    )
                )
            )

    @patch("app.service.authentication.auth_service.UsersRepository")
    @patch("app.service.authentication.auth_service.PasswordResetTokenRepository")
    @patch("app.service.authentication.auth_service.pwd_context")
    def test_reset_password_same_as_current(
        self,
        mock_pwd_context,
        mock_token_repo,
        mock_users_repo,
    ):
        """Should reject when new_password matches the current password."""
        mock_user_for_otp = MagicMock(user_id=uuid4())
        mock_token = MagicMock(token_id=uuid4(), user_id=mock_user_for_otp.user_id)

        mock_user = MagicMock(spec=Users)
        mock_user.user_id = mock_user_for_otp.user_id
        mock_user.email = "john.doe@example.com"
        mock_user.password_hash = "existing_hashed_password"

        mock_users_repo.find_by_email = AsyncMock(return_value=mock_user_for_otp)
        mock_token_repo.find_valid_otp_by_user_and_code = AsyncMock(return_value=mock_token)
        mock_users_repo.find_by_user_id = AsyncMock(return_value=mock_user)

        # Simulate new password matching current password
        mock_pwd_context.verify.return_value = True

        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        with pytest.raises(HTTPException) as exc:
            loop.run_until_complete(
                AuthService.reset_password_service(
                    ResetPasswordSchema(
                        email="john.doe@example.com",
                        otp_code="123456",
                        new_password="SamePass123!",
                        confirm_password="SamePass123!",
                    )
                )
            )

        assert exc.value.status_code == 400
        assert "New password cannot be the same as the current password" in exc.value.detail

    @patch("app.service.authentication.auth_service.UsersRepository")
    @patch("app.service.authentication.auth_service.PasswordResetTokenRepository")
    @patch("app.service.authentication.auth_service.pwd_context")
    def test_reset_password_success(
        self,
        mock_pwd_context,
        mock_token_repo,
        mock_users_repo,
    ):
        mock_user_for_otp = MagicMock(user_id=uuid4())
        mock_token = MagicMock(token_id=uuid4(), user_id=mock_user_for_otp.user_id)

        mock_user = MagicMock(spec=Users)
        mock_user.user_id = mock_user_for_otp.user_id
        mock_user.email = "john.doe@example.com"

        mock_users_repo.find_by_email = AsyncMock(return_value=mock_user_for_otp)
        mock_token_repo.find_valid_otp_by_user_and_code = AsyncMock(return_value=mock_token)
        mock_users_repo.find_by_user_id = AsyncMock(return_value=mock_user)
        mock_users_repo.update_password = AsyncMock()
        mock_token_repo.mark_token_as_used = AsyncMock()

        mock_pwd_context.verify.return_value = False
        mock_pwd_context.hash.return_value = "new_hashed_password"

        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(
            AuthService.reset_password_service(
                ResetPasswordSchema(
                    email="john.doe@example.com",
                    otp_code="123456",
                    new_password="SecurePass123!",
                    confirm_password="SecurePass123!",
                )
            )
        )

        assert result["message"] == "Password has been reset successfully"
        mock_token_repo.mark_token_as_used.assert_called_once()
        mock_users_repo.update_password.assert_called_once()


class TestForgotPasswordEdgeCases:
    def test_very_long_email(self):
        data = valid_forgot_password_data_email.copy()
        data["email"] = "a" * 100 + "@example.com"
        schema = ForgotPasswordSchema(**data)
        assert len(schema.email) > 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

