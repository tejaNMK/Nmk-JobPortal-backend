"""Unit tests for `app.service.ai_service.AIService`.

`tests/conftest.py` stubs `boto3`/`botocore` at import time so the real
AWS SDK is never required to run the suite. These tests replace
`AIService._get_client` with a fake client so we can control exactly what
"Bedrock" returns without touching the network.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field

from app.service.ai_service import AIService, AIServiceError


def _bedrock_response(text: str, usage: dict | None = None) -> dict:
    payload = {"output": {"message": {"content": [{"text": text}]}}}
    if usage is not None:
        payload["usage"] = usage
    return payload


def _service_with_fake_client(fake_client) -> AIService:
    service = AIService(model_id="test-model", region_name="us-east-1")
    service._client = fake_client
    return service


def test_invoke_returns_text_from_converse_response():
    fake_client = MagicMock()
    fake_client.converse.return_value = _bedrock_response("Hello from Bedrock")

    service = _service_with_fake_client(fake_client)
    result = service.invoke(system_prompt="sys", user_prompt="hi")

    assert result == "Hello from Bedrock"
    fake_client.converse.assert_called_once()
    _, kwargs = fake_client.converse.call_args
    assert kwargs["modelId"] == "test-model"
    assert kwargs["system"] == [{"text": "sys"}]
    assert kwargs["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]
    assert kwargs["inferenceConfig"] == {"maxTokens": 2000, "temperature": 0.2}


def test_invoke_with_usage_returns_provider_metadata():
    fake_client = MagicMock()
    fake_client.converse.return_value = _bedrock_response(
        "Hello from Bedrock",
        usage={"inputTokens": 10, "outputTokens": 4},
    )

    service = _service_with_fake_client(fake_client)
    result = service.invoke_with_usage(
        system_prompt="sys",
        user_prompt="hi",
        feature="test_feature",
        prompt_version="test_v1",
    )

    assert result.content == "Hello from Bedrock"
    assert result.input_tokens == 10
    assert result.output_tokens == 4
    assert result.model_id == "test-model"
    assert result.provider == "bedrock"
    assert result.feature == "test_feature"
    assert result.prompt_version == "test_v1"


def test_invoke_combines_text_blocks_from_converse_response():
    fake_client = MagicMock()
    fake_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "Hello "}, {"text": "from Converse"}]}},
        "usage": {"inputTokens": 11, "outputTokens": 5},
    }

    service = AIService(model_id="openai.gpt-oss-20b-1:0", region_name="us-east-1")
    service._client = fake_client
    result = service.invoke_with_usage(system_prompt="sys", user_prompt="hi")

    assert result.content == "Hello from Converse"
    assert result.input_tokens == 11
    assert result.output_tokens == 5
    _, kwargs = fake_client.converse.call_args
    assert kwargs["modelId"] == "openai.gpt-oss-20b-1:0"


class _ScorePayload(BaseModel):
    score: int = Field(..., ge=0, le=100)


def test_invoke_raises_ai_service_error_on_empty_response():
    fake_client = MagicMock()
    fake_client.converse.return_value = _bedrock_response("")

    service = _service_with_fake_client(fake_client)
    with pytest.raises(AIServiceError):
        service.invoke(system_prompt="sys", user_prompt="hi")


def test_invoke_raises_ai_service_error_on_client_error():
    from botocore.exceptions import ClientError

    fake_client = MagicMock()
    error = ClientError.__new__(ClientError)
    error.response = {"Error": {"Message": "Access denied"}}
    fake_client.converse.side_effect = error

    service = _service_with_fake_client(fake_client)
    with pytest.raises(AIServiceError):
        service.invoke(system_prompt="sys", user_prompt="hi")


def test_invoke_json_parses_plain_json():
    fake_client = MagicMock()
    fake_client.converse.return_value = _bedrock_response(
        '{"match_score": 80, "matching_skills": ["Python"]}'
    )

    service = _service_with_fake_client(fake_client)
    result = service.invoke_json(system_prompt="sys", user_prompt="hi")

    assert result == {"match_score": 80, "matching_skills": ["Python"]}


def test_invoke_json_strips_markdown_code_fences():
    fake_client = MagicMock()
    fenced = "```json\n{\"match_score\": 55}\n```"
    fake_client.converse.return_value = _bedrock_response(fenced)

    service = _service_with_fake_client(fake_client)
    result = service.invoke_json(system_prompt="sys", user_prompt="hi")

    assert result == {"match_score": 55}


def test_invoke_json_raises_ai_service_error_on_invalid_json():
    fake_client = MagicMock()
    fake_client.converse.return_value = _bedrock_response("not json at all")

    service = _service_with_fake_client(fake_client)
    with pytest.raises(AIServiceError):
        service.invoke_json(system_prompt="sys", user_prompt="hi")


def test_invoke_json_raises_ai_service_error_on_non_object_json():
    fake_client = MagicMock()
    fake_client.converse.return_value = _bedrock_response("[1, 2, 3]")

    service = _service_with_fake_client(fake_client)
    with pytest.raises(AIServiceError):
        service.invoke_json(system_prompt="sys", user_prompt="hi")


def test_invoke_json_with_usage_validates_pydantic_model():
    fake_client = MagicMock()
    fake_client.converse.return_value = _bedrock_response('{"score": 88}')

    service = _service_with_fake_client(fake_client)
    result = service.invoke_json_with_usage(
        system_prompt="sys",
        user_prompt="hi",
        response_model=_ScorePayload,
    )

    assert result.data == {"score": 88}
    assert result.parsed_model.score == 88


def test_invoke_json_with_usage_repairs_invalid_json_once():
    fake_client = MagicMock()
    fake_client.converse.side_effect = [
        _bedrock_response("not json", usage={"inputTokens": 5, "outputTokens": 2}),
        _bedrock_response('{"score": 91}', usage={"inputTokens": 7, "outputTokens": 3}),
    ]

    service = _service_with_fake_client(fake_client)
    result = service.invoke_json_with_usage(
        system_prompt="sys",
        user_prompt="hi",
        response_model=_ScorePayload,
    )

    assert result.data == {"score": 91}
    assert result.input_tokens == 12
    assert result.output_tokens == 5
    assert fake_client.converse.call_count == 2


def test_model_id_and_region_default_from_env(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "env-model")
    monkeypatch.setenv("BEDROCK_REGION", "eu-west-1")

    service = AIService()

    assert service._model_id == "env-model"
    assert service._region_name == "eu-west-1"


def test_constructor_args_override_env(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "env-model")

    service = AIService(model_id="explicit-model")

    assert service._model_id == "explicit-model"


def test_dedicated_bedrock_credentials_precede_shared_aws_credentials(monkeypatch):
    import app.service.ai_service as ai_service_module

    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = MagicMock()
    monkeypatch.setattr(ai_service_module, "boto3", fake_boto3)
    monkeypatch.setattr(ai_service_module, "BotoConfig", None)
    monkeypatch.setenv("BEDROCK_ACCESS_KEY_ID", "bedrock-key")
    monkeypatch.setenv("BEDROCK_SECRET_ACCESS_KEY", "bedrock-secret")
    monkeypatch.setenv("BEDROCK_SESSION_TOKEN", "bedrock-token")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aws-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "aws-token")

    AIService(model_id="test-model", region_name="us-east-1")._get_client()

    _, kwargs = fake_boto3.client.call_args
    assert kwargs["aws_access_key_id"] == "bedrock-key"
    assert kwargs["aws_secret_access_key"] == "bedrock-secret"
    assert kwargs["aws_session_token"] == "bedrock-token"
