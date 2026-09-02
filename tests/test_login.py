"""Tests for login endpoint"""
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from pydantic import ValidationError

from app.schema.auth import LoginSchema
from app.service.authentication.auth_service import AuthService
from app.repository.authentication.users import UsersRepository
from app.model.authentication.users import Users


valid_login_data = {
    "email": "john.doe@example.com",
    "password": "SecurePass123!"
}


class TestLoginSchema:
    """Test LoginSchema validation"""

    def test_valid_login_data(self):
        """Test that valid email and password passes validation"""
        data = valid_login_data.copy()
        schema = LoginSchema(**data)
        assert schema.email == "john.doe@example.com"
        assert schema.password == "SecurePass123!"

    def test_missing_email(self):
        """Test that missing email raises error"""
        data = valid_login_data.copy()
        del data["email"]
        with pytest.raises(ValidationError, match="email"):
            LoginSchema(**data)

    def test_missing_password(self):
        """Test that missing password raises error"""
        data = valid_login_data.copy()
        del data["password"]
        with pytest.raises(ValidationError):
            LoginSchema(**data)

    def test_empty_email(self):
        """Test that empty email raises error"""
        data = valid_login_data.copy()
        data["email"] = ""
        with pytest.raises(ValidationError):
            LoginSchema(**data)

    def test_invalid_email_format(self):
        """Test that invalid email format raises error"""
        data = valid_login_data.copy()
        data["email"] = "invalid-email"
        with pytest.raises(ValidationError):
            LoginSchema(**data)

    def test_email_without_domain(self):
        """Test that email without domain raises error"""
        data = valid_login_data.copy()
        data["email"] = "user@"
        with pytest.raises(ValidationError):
            LoginSchema(**data)

    def test_email_with_special_characters(self):
        """Test that special characters in email are accepted"""
        data = valid_login_data.copy()
        data["email"] = "user+tag@example.co.uk"
        schema = LoginSchema(**data)
        assert schema.email == "user+tag@example.co.uk"

    def test_email_case_normalized(self):
        """Test that EmailStr lowercases the domain"""
        data = valid_login_data.copy()
        data["email"] = "John.Doe@Example.COM"
        schema = LoginSchema(**data)
        assert schema.email == "John.Doe@example.com"


class TestLoginService:
    """Test login service logic with mocked dependencies"""

    def test_login_user_not_found(self):
        """Test login with non-existent email raises 404"""
        with patch.object(UsersRepository, "find_by_email", new_callable=AsyncMock, return_value=None):
            from fastapi import HTTPException
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            with pytest.raises(HTTPException, match="User not found"):
                loop.run_until_complete(
                    AuthService.login_service(LoginSchema(**valid_login_data))
                )

    @patch("app.service.authentication.auth_service.pwd_context")
    def test_login_wrong_password(self, mock_pwd_context):
        """Test login with wrong password raises 400"""
        mock_user = MagicMock(spec=Users)
        mock_user.user_id = "test-uuid"
        mock_user.email = "john.doe@example.com"
        mock_user.password_hash = "hashed_password"

        mock_pwd_context.verify.return_value = False

        with patch.object(UsersRepository, "find_by_email", new_callable=AsyncMock, return_value=mock_user):
            from fastapi import HTTPException
            import asyncio

            data = valid_login_data.copy()
            data["password"] = "WrongPassword123!"

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            with pytest.raises(HTTPException, match="Invalid password"):
                loop.run_until_complete(
                    AuthService.login_service(LoginSchema(**data))
                )

    @patch("app.service.authentication.auth_service.pwd_context")
    @patch("app.service.authentication.auth_service.JWTRepo")
    def test_login_success(self, mock_jwt_repo, mock_pwd_context):
        """Test successful login returns token"""
        mock_user = MagicMock(spec=Users)
        mock_user.user_id = "test-uuid"
        mock_user.email = "john.doe@example.com"
        mock_user.password_hash = "hashed_password"

        mock_pwd_context.verify.return_value = True

        mock_jwt_instance = MagicMock()
        mock_jwt_instance.generate_token.return_value = "test.jwt.token"
        mock_jwt_repo.return_value = mock_jwt_instance

        with patch.object(UsersRepository, "find_by_email", new_callable=AsyncMock, return_value=mock_user):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(
                AuthService.login_service(LoginSchema(**valid_login_data))
            )

            assert "access_token" in result
            assert result["token_type"] == "bearer"


class TestLoginEdgeCases:
    """Test edge cases for login"""

    def test_very_long_email(self):
        """Test with very long email"""
        data = valid_login_data.copy()
        data["email"] = "a" * 100 + "@example.com"
        schema = LoginSchema(**data)
        assert len(schema.email) > 50

    def test_very_long_password(self):
        """Test with very long password"""
        data = valid_login_data.copy()
        data["password"] = "p" * 200
        schema = LoginSchema(**data)
        assert len(schema.password) == 200

    def test_password_with_unicode(self):
        """Test password with unicode characters"""
        data = valid_login_data.copy()
        data["password"] = "SecurePass123!®™©"
        schema = LoginSchema(**data)
        assert schema.password == "SecurePass123!®™©"

    def test_email_subdomain(self):
        """Test email with subdomain"""
        data = valid_login_data.copy()
        data["email"] = "user@mail.example.com"
        schema = LoginSchema(**data)
        assert schema.email == "user@mail.example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
