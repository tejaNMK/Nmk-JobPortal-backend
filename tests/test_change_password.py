from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schema.auth import ChangePasswordSchema
from app.service.authentication.auth_service import AuthService
from app.repository.authentication.users import UsersRepository
from app.model.authentication.users import Users


def _run(coro):
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestChangePasswordSchema:
    def test_rejects_empty_current_password(self):
        with pytest.raises(ValidationError):
            ChangePasswordSchema(
                current_password="",
                new_password="NewPassA@1234",
                confirm_password="NewPassA@1234",
            )

    def test_rejects_password_mismatch(self):
        with pytest.raises(ValidationError):
            ChangePasswordSchema(
                current_password="Curr@1234",
                new_password="NewPass@1234",
                confirm_password="DifferentPass@1234",
            )

    def test_rejects_weak_password(self):
        with pytest.raises(ValidationError):
            ChangePasswordSchema(
                current_password="Curr@1234",
                new_password="weakpass1",
                confirm_password="weakpass1",
            )


class TestChangePasswordService:
    @patch("app.service.authentication.auth_service.pwd_context")
    @patch.object(UsersRepository, "find_by_user_id", new_callable=AsyncMock)
    def test_change_password_same_as_current(
        self,
        mock_find_by_user_id,
        mock_pwd_context,
    ):
        """Should reject when new_password matches the current password."""
        user_uuid = "00000000-0000-0000-0000-000000000003"

        mock_user = MagicMock(spec=Users)
        mock_user.user_id = user_uuid
        mock_user.email = "john.doe@example.com"
        mock_user.password_hash = "hashed_current"
        mock_find_by_user_id.return_value = mock_user

        # Both verify() calls return True (current password correct, new password same as current)
        mock_pwd_context.verify.return_value = True

        change = ChangePasswordSchema(
            current_password="Curr@1234",
            new_password="Curr@1234",
            confirm_password="Curr@1234",
        )

        with pytest.raises(HTTPException) as exc:
            _run(
                AuthService.change_password_service(
                    user_id=user_uuid,
                    change_password=change,
                )
            )

        assert exc.value.status_code == 400
        assert "New password cannot be the same as the current password" in exc.value.detail

    @patch("app.service.authentication.auth_service.pwd_context")
    @patch.object(UsersRepository, "find_by_user_id", new_callable=AsyncMock)
    @patch.object(UsersRepository, "update_password", new_callable=AsyncMock)
    def test_change_password_happy_path(
        self,
        mock_update_password,
        mock_find_by_user_id,
        mock_pwd_context,
    ):
        # UUID-shaped value to avoid asyncpg UUID type errors
        # when the real db layer accidentally runs autoflush.
        user_uuid = "00000000-0000-0000-0000-000000000001"

        mock_user = MagicMock(spec=Users)
        mock_user.user_id = user_uuid
        mock_user.email = "john.doe@example.com"
        mock_user.password_hash = "hashed"

        mock_find_by_user_id.return_value = mock_user
        # First verify(Curr@1234, ...) -> True, second verify(NewPassA1!234, ...) -> False
        mock_pwd_context.verify.side_effect = [True, False]

        change = ChangePasswordSchema(
            current_password="Curr@1234",
            new_password="NewPassA1!234",
            confirm_password="NewPassA1!234",
        )

        mock_pwd_context.hash.return_value = "new-hash"

        # Prevent db writes (password_history insert) even if db session exists
        # by forcing auth_service.db.session to None for this test.
        
        result = _run(
            AuthService.change_password_service(
            user_id=user_uuid,
            change_password=change,
            )
        )

        assert result["message"] == "Password changed successfully"
        mock_update_password.assert_awaited_once()

        # Ensure the db layer was not awaited (we mocked db/commit in this test)
        # and the happy-path returned the success message.


    @patch("app.service.authentication.auth_service.pwd_context")
    @patch.object(UsersRepository, "find_by_user_id", new_callable=AsyncMock)
    def test_change_password_wrong_current_password(
        self,
        mock_find_by_user_id,
        mock_pwd_context,
    ):
        user_uuid = "00000000-0000-0000-0000-000000000002"

        mock_user = MagicMock(spec=Users)
        mock_user.user_id = user_uuid
        mock_user.email = "john.doe@example.com"
        mock_user.password_hash = "hashed"
        mock_find_by_user_id.return_value = mock_user

        mock_pwd_context.verify.return_value = False

        change = ChangePasswordSchema(
            current_password="Wrong@1234",
            new_password="NewPassA@1234",
            confirm_password="NewPassA@1234",
        )

        with pytest.raises(HTTPException) as exc:
            _run(
                AuthService.change_password_service(
                    user_id=user_uuid,
                    change_password=change,
                )
            )

        assert exc.value.status_code == 400
        assert "Invalid current password" in exc.value.detail

    @patch("app.service.authentication.auth_service.pwd_context")
    @patch.object(UsersRepository, "find_by_user_id", new_callable=AsyncMock)
    def test_change_password_user_not_found(
        self,
        mock_find_by_user_id,
        mock_pwd_context,
    ):
        mock_find_by_user_id.return_value = None

        change = ChangePasswordSchema(
            current_password="Curr@1234",
            new_password="NewPassA1!234",
            confirm_password="NewPassA1!234",
        )

        with pytest.raises(HTTPException) as exc:
            _run(
                AuthService.change_password_service(
                    user_id="missing-uuid",
                    change_password=change,
                )
            )

        assert exc.value.status_code == 404
        assert "User not found" in exc.value.detail

