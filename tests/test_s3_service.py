from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi import HTTPException

from app.service import s3_service


def test_get_object_size_returns_content_length_on_success():
    fake_client = type(
        "FakeClient", (), {"head_object": lambda self, **kwargs: {"ContentLength": 251_000}}
    )()
    with patch.object(s3_service, "_s3_client", return_value=fake_client), patch.object(
        s3_service, "_bucket", return_value="test-bucket"
    ):
        assert s3_service.get_object_size("resumes/candidate-1/resume.pdf") == 251_000


def test_get_object_size_returns_none_on_missing_object():
    def raise_client_error(self, **kwargs):
        raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")

    fake_client = type("FakeClient", (), {"head_object": raise_client_error})()
    with patch.object(s3_service, "_s3_client", return_value=fake_client), patch.object(
        s3_service, "_bucket", return_value="test-bucket"
    ):
        assert s3_service.get_object_size("resumes/candidate-1/missing.pdf") is None


def test_get_object_size_returns_none_instead_of_raising_on_unexpected_error():
    """This is the exact class of bug that caused the 500 in production:
    a non-ClientError failure (missing credentials, misconfigured bucket,
    network error, etc.) must not propagate — it must degrade to None."""

    def raise_runtime_error(self, **kwargs):
        raise RuntimeError("boom")

    fake_client = type("FakeClient", (), {"head_object": raise_runtime_error})()
    with patch.object(s3_service, "_s3_client", return_value=fake_client), patch.object(
        s3_service, "_bucket", return_value="test-bucket"
    ):
        assert s3_service.get_object_size("resumes/candidate-1/resume.pdf") is None


def test_get_object_size_returns_none_when_bucket_env_var_missing():
    """_bucket() raises RuntimeError (not ClientError) when S3_BUCKET_NAME
    isn't set — this must also degrade to None, not raise."""
    with patch.object(s3_service, "_bucket", side_effect=RuntimeError("S3_BUCKET_NAME environment variable is required")):
        assert s3_service.get_object_size("resumes/candidate-1/resume.pdf") is None


def test_fetch_object_bytes_returns_content_on_success():
    fake_body = type("FakeBody", (), {"read": lambda self: b"%PDF-1.4 bytes"})()
    fake_client = type(
        "FakeClient",
        (),
        {"get_object": lambda self, **kwargs: {"Body": fake_body, "ContentType": "application/pdf"}},
    )()
    with patch.object(s3_service, "_s3_client", return_value=fake_client), patch.object(
        s3_service, "_bucket", return_value="test-bucket"
    ):
        content, content_type = s3_service.fetch_object_bytes("resumes/candidate-1/resume.pdf")
        assert content == b"%PDF-1.4 bytes"
        assert content_type == "application/pdf"


def test_fetch_object_bytes_raises_404_on_missing_object():
    def raise_client_error(self, **kwargs):
        raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject")

    fake_client = type("FakeClient", (), {"get_object": raise_client_error})()
    with patch.object(s3_service, "_s3_client", return_value=fake_client), patch.object(
        s3_service, "_bucket", return_value="test-bucket"
    ):
        with pytest.raises(HTTPException) as exc_info:
            s3_service.fetch_object_bytes("resumes/candidate-1/missing.pdf")
        assert exc_info.value.status_code == 404


def test_fetch_object_bytes_raises_503_on_connection_failure():
    """Regression test for the exact bug seen in production logs: the
    backend's own network to S3 drops (DNS failure / EndpointConnectionError),
    which is a different failure mode than a ClientError (S3 responding with
    a rejection). This must degrade to a clean 503, not an unhandled 500."""

    def raise_connection_error(self, **kwargs):
        raise EndpointConnectionError(endpoint_url="https://test-bucket.s3.amazonaws.com/resumes/x.pdf")

    fake_client = type("FakeClient", (), {"get_object": raise_connection_error})()
    with patch.object(s3_service, "_s3_client", return_value=fake_client), patch.object(
        s3_service, "_bucket", return_value="test-bucket"
    ):
        with pytest.raises(HTTPException) as exc_info:
            s3_service.fetch_object_bytes("resumes/candidate-1/resume.pdf")
        assert exc_info.value.status_code == 503