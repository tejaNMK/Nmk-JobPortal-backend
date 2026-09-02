"""Repository package.

This file exists to keep backwards-compatible import paths used by tests.
"""

# Re-export authentication repo module so tests can patch
# `app.repository.auth_repo.JWTBearer.__call__`.
from . import auth_repo  # noqa: F401

