"""Employer-side AWS Bedrock integration.

Employer AI features should go through this module rather than the shared
candidate/current AI service. This keeps employer model defaults,
credentials, timeouts, provider behavior, JSON repair, and error mapping
isolated from candidate AI work.

Talks to Bedrock Runtime through the Converse API.

Employer-specific environment variables are preferred first:
    EMPLOYER_BEDROCK_ACCESS_KEY_ID / EMPLOYER_BEDROCK_SECRET_ACCESS_KEY
    EMPLOYER_AWS_ACCESS_KEY_ID / EMPLOYER_AWS_SECRET_ACCESS_KEY
    EMPLOYER_BEDROCK_SESSION_TOKEN / EMPLOYER_AWS_SESSION_TOKEN
    EMPLOYER_BEDROCK_REGION / EMPLOYER_AWS_REGION
    EMPLOYER_BEDROCK_MODEL_ID / EMPLOYER_AI_MODEL
    EMPLOYER_BEDROCK_TIMEOUT_SECONDS

Shared AWS/Bedrock variables remain fallback-only to preserve existing
deployments while allowing employer AI to diverge independently.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

from pydantic import ValidationError

import app.config  # noqa: F401 - load project environment before reading AI env vars


try:
    import boto3
except Exception:  # pragma: no cover - defensive, mirrors s3_service.py
    boto3 = None

try:
    from botocore.exceptions import (
        BotoCoreError,
        ClientError,
        EndpointConnectionError,
        ReadTimeoutError,
    )
except Exception:  # pragma: no cover - defensive, mirrors s3_service.py
    ClientError = Exception
    BotoCoreError = Exception
    EndpointConnectionError = Exception
    ReadTimeoutError = Exception

try:
    from botocore.config import Config as BotoConfig
except Exception:  # pragma: no cover - defensive, mirrors s3_service.py
    BotoConfig = None


DEFAULT_BEDROCK_MODEL_ID = "openai.gpt-oss-20b-1:0"
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT_SECONDS = 30
JSON_REPAIR_MAX_TOKENS = 1200
AI_ERROR_HTTP_STATUS = {
    "PROVIDER_UNAVAILABLE": 503,
    "PROVIDER_TIMEOUT": 504,
    "PROVIDER_REJECTED": 502,
    "BAD_PROVIDER_RESPONSE": 502,
    "EMPTY_RESPONSE": 502,
    "INVALID_JSON": 502,
    "INVALID_JSON_SHAPE": 502,
    "SCHEMA_VALIDATION_FAILED": 502,
}

T = TypeVar("T")


@dataclass(frozen=True)
class AIInvocationResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model_id: str = ""
    provider: str = "bedrock"
    latency_ms: int = 0
    feature: str | None = None
    prompt_version: str | None = None


@dataclass(frozen=True)
class AIJSONInvocationResult(Generic[T]):
    data: Dict[str, Any]
    content: str
    parsed_model: T | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    model_id: str = ""
    provider: str = "bedrock"
    latency_ms: int = 0
    feature: str | None = None
    prompt_version: str | None = None
    repaired: bool = False
    repair_attempts: int = 0


class AIServiceError(Exception):
    """Raised when AWS Bedrock is unreachable, rejects the request, or
    returns output the caller can't use (empty text / invalid JSON).

    Callers (service layer) are expected to catch this and translate it
    into the API's standard error response instead of letting a raw
    botocore exception surface.
    """

    def __init__(self, message: str, *, category: str = "PROVIDER_ERROR") -> None:
        super().__init__(message)
        self.category = category


class AIService:
    """Employer-specific wrapper around the AWS Bedrock Runtime Converse API.

    Instances are cheap and stateless aside from a lazily-created boto3
    client. Model id and region are constructor-injectable so tests and
    future employer services can point at different models without
    affecting candidate AI.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        region_name: Optional[str] = None,
    ) -> None:
        self._model_id = (
            model_id
            or os.getenv("EMPLOYER_BEDROCK_MODEL_ID")
            or os.getenv("EMPLOYER_AI_MODEL")
            or os.getenv("BEDROCK_MODEL_ID")
            or DEFAULT_BEDROCK_MODEL_ID
        )
        self._region_name = region_name or os.getenv(
            "EMPLOYER_BEDROCK_REGION",
            os.getenv(
                "EMPLOYER_AWS_REGION",
                os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1")),
            ),
        )
        self._client = None

    def _get_client(self):
        if boto3 is None:
            raise AIServiceError("boto3 is required for AWS Bedrock integration")
        if self._client is None:
            client_kwargs = {
                "aws_access_key_id": os.getenv("EMPLOYER_BEDROCK_ACCESS_KEY_ID")
                or os.getenv("EMPLOYER_AWS_ACCESS_KEY_ID")
                or os.getenv("BEDROCK_ACCESS_KEY_ID")
                or os.getenv("AWS_ACCESS_KEY_ID"),
                "aws_secret_access_key": os.getenv("EMPLOYER_BEDROCK_SECRET_ACCESS_KEY")
                or os.getenv("EMPLOYER_AWS_SECRET_ACCESS_KEY")
                or os.getenv("BEDROCK_SECRET_ACCESS_KEY")
                or os.getenv("AWS_SECRET_ACCESS_KEY"),
                "aws_session_token": os.getenv("EMPLOYER_BEDROCK_SESSION_TOKEN")
                or os.getenv("EMPLOYER_AWS_SESSION_TOKEN")
                or os.getenv("BEDROCK_SESSION_TOKEN")
                or os.getenv("AWS_SESSION_TOKEN"),
                "region_name": self._region_name,
            }
            timeout_seconds = _positive_float_env(
                "EMPLOYER_BEDROCK_TIMEOUT_SECONDS",
                _positive_float_env("BEDROCK_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
            )
            if BotoConfig is not None:
                client_kwargs["config"] = BotoConfig(
                    connect_timeout=timeout_seconds,
                    read_timeout=timeout_seconds,
                    retries={"max_attempts": 2, "mode": "standard"},
                )
            self._client = boto3.client(
                "bedrock-runtime",
                **client_kwargs,
            )
        return self._client

    def invoke_with_usage(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        feature: str | None = None,
        prompt_version: str | None = None,
    ) -> AIInvocationResult:
        """Invoke the configured Bedrock model and return the raw text
        completion. Raises `AIServiceError` on any failure."""

        client = self._get_client()
        started = time.monotonic()

        try:
            response = client.converse(
                modelId=self._model_id,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": user_prompt}],
                    }
                ],
                inferenceConfig={
                    "maxTokens": max_tokens,
                    "temperature": temperature,
                },
            )
        except ClientError as exc:
            logger.exception("Bedrock converse was rejected.")
            message = getattr(exc, "response", {}).get("Error", {}).get("Message", str(exc))
            raise AIServiceError(
                f"AI service request failed: {message}",
                category="PROVIDER_REJECTED",
            ) from exc
        except ReadTimeoutError as exc:
            logger.exception("AWS Bedrock request timed out.")
            raise AIServiceError(
                "The AI service timed out. Please try again.",
                category="PROVIDER_TIMEOUT",
            ) from exc
        except (EndpointConnectionError, ConnectionError, BotoCoreError) as exc:
            logger.exception("Could not reach AWS Bedrock.")
            raise AIServiceError(
                "Could not reach the AI service. Please try again.",
                category="PROVIDER_UNAVAILABLE",
            ) from exc

        try:
            usage = response.get("usage") or {}
        except Exception as exc:
            logger.exception("Failed to parse the Bedrock Converse response.")
            raise AIServiceError(
                "Received an unreadable response from the AI service.",
                category="BAD_PROVIDER_RESPONSE",
            ) from exc

        text = _extract_bedrock_text(response)
        if not text:
            raise AIServiceError(
                "The AI service returned an empty response.",
                category="EMPTY_RESPONSE",
            )
        result = AIInvocationResult(
            content=text,
            input_tokens=int(usage.get("inputTokens") or 0),
            output_tokens=int(usage.get("outputTokens") or 0),
            model_id=self._model_id,
            latency_ms=int((time.monotonic() - started) * 1000),
            feature=feature,
            prompt_version=prompt_version,
        )
        logger.info(
            "AI invocation succeeded.",
            extra={
                "provider": result.provider,
                "model": result.model_id,
                "feature": feature,
                "prompt_version": prompt_version,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": result.latency_ms,
            },
        )
        return result

    def invoke(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        """Invoke the configured Bedrock model and return the raw text
        completion. Raises `AIServiceError` on any failure."""

        return self.invoke_with_usage(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        ).content

    def invoke_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> Dict[str, Any]:
        """Invoke the model and parse its completion as a JSON object.

        Strips a markdown code fence if the model wraps its JSON in one
        despite instructions not to, then parses strictly. Raises
        `AIServiceError` (not a raw `json.JSONDecodeError`) on invalid
        JSON so callers can surface a clean error response.
        """

        return self.invoke_json_with_usage(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        ).data

    def invoke_json_with_usage(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        response_model: type[T] | None = None,
        feature: str | None = None,
        prompt_version: str | None = None,
        repair_on_invalid: bool = True,
    ) -> AIJSONInvocationResult[T]:
        raw = self.invoke_with_usage(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            feature=feature,
            prompt_version=prompt_version,
        )

        try:
            return _parse_json_invocation_result(
                raw,
                response_model=response_model,
            )
        except AIServiceError as first_error:
            if not repair_on_invalid:
                raise
            repaired = self._repair_json_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                invalid_response=raw.content,
                validation_error=str(first_error),
                max_tokens=max_tokens,
                feature=feature,
                prompt_version=prompt_version,
            )
            try:
                parsed = _parse_json_invocation_result(
                    repaired,
                    response_model=response_model,
                )
            except AIServiceError:
                logger.warning(
                    "AI JSON repair failed.",
                    extra={
                        "provider": raw.provider,
                        "model": raw.model_id,
                        "feature": feature,
                        "prompt_version": prompt_version,
                    },
                    exc_info=True,
                )
                raise first_error
            return AIJSONInvocationResult(
                data=parsed.data,
                content=parsed.content,
                parsed_model=parsed.parsed_model,
                input_tokens=raw.input_tokens + repaired.input_tokens,
                output_tokens=raw.output_tokens + repaired.output_tokens,
                model_id=parsed.model_id,
                provider=parsed.provider,
                latency_ms=raw.latency_ms + repaired.latency_ms,
                feature=feature,
                prompt_version=prompt_version,
                repaired=True,
                repair_attempts=1,
            )

    async def ainvoke_with_usage(self, **kwargs) -> AIInvocationResult:
        import asyncio

        return await asyncio.to_thread(self.invoke_with_usage, **kwargs)

    async def ainvoke_json_with_usage(self, **kwargs) -> AIJSONInvocationResult[Any]:
        import asyncio

        return await asyncio.to_thread(self.invoke_json_with_usage, **kwargs)

    def _repair_json_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        invalid_response: str,
        validation_error: str,
        max_tokens: int,
        feature: str | None,
        prompt_version: str | None,
    ) -> AIInvocationResult:
        repair_system_prompt = "\n".join(
            [
                system_prompt,
                "The previous response was invalid.",
                "Return only a valid JSON object for the original request.",
                "Do not include markdown, commentary, or code fences.",
            ]
        )
        repair_user_prompt = "\n\n".join(
            [
                "Original request:",
                user_prompt,
                "Invalid response:",
                invalid_response[:2000],
                "Validation error:",
                validation_error[:1000],
            ]
        )
        return self.invoke_with_usage(
            system_prompt=repair_system_prompt,
            user_prompt=repair_user_prompt,
            max_tokens=min(max_tokens, JSON_REPAIR_MAX_TOKENS),
            temperature=0,
            feature=feature,
            prompt_version=prompt_version,
        )


def _parse_json_invocation_result(
    result: AIInvocationResult,
    *,
    response_model: type[T] | None = None,
) -> AIJSONInvocationResult[T]:
    cleaned = _strip_code_fences(result.content)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("AI service returned invalid JSON: %s", cleaned[:500])
        raise AIServiceError(
            "The AI service returned an invalid response format.",
            category="INVALID_JSON",
        ) from exc

    if not isinstance(parsed, dict):
        logger.error("AI service returned non-object JSON: %s", cleaned[:500])
        raise AIServiceError(
            "The AI service returned an unexpected response shape.",
            category="INVALID_JSON_SHAPE",
        )

    parsed_model = None
    if response_model is not None:
        try:
            parsed_model = response_model.model_validate(parsed)
        except (AttributeError, ValidationError, ValueError, TypeError) as exc:
            raise AIServiceError(
                "The AI service returned an invalid response schema.",
                category="SCHEMA_VALIDATION_FAILED",
            ) from exc

    return AIJSONInvocationResult(
        data=parsed,
        content=cleaned,
        parsed_model=parsed_model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        model_id=result.model_id,
        provider=result.provider,
        latency_ms=result.latency_ms,
        feature=result.feature,
        prompt_version=result.prompt_version,
    )


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def _extract_bedrock_text(payload: dict[str, Any]) -> str:
    content = ((payload.get("output") or {}).get("message") or {}).get("content") or []
    text_parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    return _strip_reasoning_preamble("".join(text_parts).strip())


_REASONING_BLOCK_RE = re.compile(
    r"<reasoning>.*?</reasoning>",
    re.DOTALL | re.IGNORECASE,
)


def _strip_reasoning_preamble(text: str) -> str:
    """
    Removes GPT-OSS reasoning blocks before returning the response to callers.
    """
    if not text:
        return text

    return _REASONING_BLOCK_RE.sub("", text).strip()


def _positive_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; expected a positive number.", name, value)
        return default
    return parsed if parsed > 0 else default


def ai_error_status_code(error: AIServiceError) -> int:
    return AI_ERROR_HTTP_STATUS.get(error.category, 502)
