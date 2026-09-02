"""Model package.

Intentionally does not import all models to avoid import-order side effects.
Use app.model.mapper_bootstrap.bootstrap_mappers() at startup.
"""

from .authentication.mapper_bootstrap import bootstrap_mappers

__all__ = [
    "bootstrap_mappers",
    "Users",
    "UsersRole",
    "PasswordHistory",
    "Role",
    "UserSession",
    "PasswordResetToken",
]


def __getattr__(name: str):
    if name == "Users":
        from app.model.authentication.users import Users
        return Users

    if name == "UsersRole":
        from app.model.authentication.user_role import UsersRole
        return UsersRole

    if name == "PasswordHistory":
        from app.model.authentication.password_history import PasswordHistory
        return PasswordHistory

    if name == "Role":
        from app.model.authentication.role import Role
        return Role

    if name == "UserSession":
        from app.model.authentication.user_session import UserSession
        return UserSession

    if name == "PasswordResetToken":
        from app.model.authentication.password_reset_token import PasswordResetToken
        return PasswordResetToken

    raise AttributeError(name)