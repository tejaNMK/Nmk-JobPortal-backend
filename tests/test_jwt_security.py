from datetime import timedelta

import pytest
from jose import jwt

from app import config
from app.repository.authentication import auth_repo
from app.repository.authentication.auth_repo import JWTRepo


def test_missing_jwt_secret_is_rejected():
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        config.validate_jwt_secret_key(None)


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "   ",
        "mysecretkey",
        "secret",
        "changeme",
        "short-but-not-default",
    ],
)
def test_weak_or_default_jwt_secret_is_rejected(secret):
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        config.validate_jwt_secret_key(secret)


def test_valid_secure_jwt_secret_is_accepted():
    secure_secret = (
        "test-only-secure-jwt-secret-64-bytes-minimum-value-for-validation"
    )

    assert config.validate_jwt_secret_key(secure_secret) == secure_secret


def test_jwt_algorithm_env_value_is_used():
    assert config.get_jwt_algorithm("HS512") == "HS512"
    assert config.get_jwt_algorithm("  HS384  ") == "HS384"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_jwt_algorithm_defaults_to_hs256(value):
    assert config.get_jwt_algorithm(value) == config.DEFAULT_JWT_ALGORITHM
    assert config.DEFAULT_JWT_ALGORITHM == "HS256"


def test_token_generation_and_validation_use_secure_jwt_secret(monkeypatch):
    secure_secret = (
        "test-only-secure-jwt-secret-for-token-generation-and-validation-64"
    )
    monkeypatch.setattr(auth_repo, "JWT_SECRET_KEY", secure_secret)

    token = JWTRepo(
        data={
            "user_id": "user-123",
            "email": "person@example.com",
        }
    ).generate_token(expires_delta=timedelta(minutes=5))

    payload = JWTRepo.extract_token(token)

    assert payload["user_id"] == "user-123"
    assert payload["email"] == "person@example.com"
    assert payload["jti"]
    assert payload["exp"]


def test_token_signed_with_old_secret_is_rejected(monkeypatch):
    secure_secret = (
        "test-only-new-secure-jwt-secret-after-rotation-64-bytes-minimum"
    )
    old_secret = "mysecretkey"
    monkeypatch.setattr(auth_repo, "JWT_SECRET_KEY", secure_secret)

    old_token = jwt.encode(
        {
            "user_id": "user-123",
            "email": "person@example.com",
            "jti": "old-token-id",
        },
        old_secret,
        algorithm=config.ALGORITHM,
    )

    assert JWTRepo.extract_token(old_token) is None


def test_token_creation_and_decoding_work_with_default_algorithm(monkeypatch):
    secure_secret = (
        "test-only-secure-jwt-secret-for-default-algorithm-validation-64"
    )
    monkeypatch.setattr(auth_repo, "JWT_SECRET_KEY", secure_secret)
    monkeypatch.setattr(auth_repo, "ALGORITHM", config.DEFAULT_JWT_ALGORITHM)

    token = JWTRepo(data={"user_id": "user-123"}).generate_token(
        expires_delta=timedelta(minutes=5)
    )

    header = jwt.get_unverified_header(token)
    payload = JWTRepo.extract_token(token)

    assert header["alg"] == "HS256"
    assert payload["user_id"] == "user-123"
    assert payload["jti"]


def test_tampered_token_is_rejected_with_default_algorithm(monkeypatch):
    secure_secret = (
        "test-only-secure-jwt-secret-for-tampered-token-validation-64"
    )
    monkeypatch.setattr(auth_repo, "JWT_SECRET_KEY", secure_secret)
    monkeypatch.setattr(auth_repo, "ALGORITHM", config.DEFAULT_JWT_ALGORITHM)

    token = JWTRepo(data={"user_id": "user-123"}).generate_token(
        expires_delta=timedelta(minutes=5)
    )
    header, payload, signature = token.split(".")
    replacement = "a" if signature[0] != "a" else "b"
    tampered_token = f"{header}.{payload}.{replacement}{signature[1:]}"

    assert JWTRepo.extract_token(tampered_token) is None
