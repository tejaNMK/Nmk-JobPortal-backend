from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.service.ai_service import AIService, AIServiceError


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIProviderRequest:
    system_prompt: str
    user_prompt: str
    max_tokens: int
    temperature: float
    feature: str
    prompt_version: str
    response_model: type | None = None


@dataclass(frozen=True)
class AIProviderResponse:
    content: str
    data: dict[str, Any] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = ""
    model_id: str = ""
    latency_ms: int = 0
    repaired: bool = False
    repair_attempts: int = 0


class AIProvider(ABC):
    provider_name: str
    model_id: str

    @abstractmethod
    async def generate_json(self, request: AIProviderRequest) -> AIProviderResponse:
        raise NotImplementedError

    async def stream_text(self, request: AIProviderRequest):
        response = await self.generate_json(request)
        text = response.content
        chunk_size = 240
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]


class BedrockAIProvider(AIProvider):
    provider_name = "bedrock"

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    async def generate_json(self, request: AIProviderRequest) -> AIProviderResponse:
        result = await AIService(model_id=self.model_id).ainvoke_json_with_usage(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            response_model=request.response_model,
            feature=request.feature,
            prompt_version=request.prompt_version,
        )
        return AIProviderResponse(
            content=result.content,
            data=result.data,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            provider=result.provider,
            model_id=result.model_id,
            latency_ms=result.latency_ms,
            repaired=result.repaired,
            repair_attempts=result.repair_attempts,
        )


class OpenAICompatibleProvider(AIProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        model_id: str,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.provider_name = provider_name
        self.model_id = model_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def generate_json(self, request: AIProviderRequest) -> AIProviderResponse:
        started = time.monotonic()
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_id,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = await _post_json(url, headers=headers, payload=payload, timeout=self.timeout_seconds)
        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content") or "").strip()
        if not content:
            raise AIServiceError("AI provider returned an empty response.", category="EMPTY_RESPONSE")
        usage = data.get("usage") or {}
        parsed = _parse_json(content)
        return AIProviderResponse(
            content=json.dumps(parsed, ensure_ascii=False),
            data=parsed,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            provider=self.provider_name,
            model_id=self.model_id,
            latency_ms=int((time.monotonic() - started) * 1000),
        )


class AnthropicProvider(AIProvider):
    provider_name = "anthropic"

    def __init__(self, *, model_id: str, api_key: str, timeout_seconds: float) -> None:
        self.model_id = model_id
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def generate_json(self, request: AIProviderRequest) -> AIProviderResponse:
        started = time.monotonic()
        payload = {
            "model": self.model_id,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
        }
        data = await _post_json(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            payload=payload,
            timeout=self.timeout_seconds,
        )
        content = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if not content:
            raise AIServiceError("AI provider returned an empty response.", category="EMPTY_RESPONSE")
        usage = data.get("usage") or {}
        parsed = _parse_json(content)
        return AIProviderResponse(
            content=json.dumps(parsed, ensure_ascii=False),
            data=parsed,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            provider=self.provider_name,
            model_id=self.model_id,
            latency_ms=int((time.monotonic() - started) * 1000),
        )


class GeminiProvider(AIProvider):
    provider_name = "gemini"

    def __init__(self, *, model_id: str, api_key: str, timeout_seconds: float) -> None:
        self.model_id = model_id
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def generate_json(self, request: AIProviderRequest) -> AIProviderResponse:
        started = time.monotonic()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_id}:generateContent?key={self.api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": request.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": request.user_prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "responseMimeType": "application/json",
            },
        }
        data = await _post_json(url, headers={}, payload=payload, timeout=self.timeout_seconds)
        candidate = (data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        content = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        if not content:
            raise AIServiceError("AI provider returned an empty response.", category="EMPTY_RESPONSE")
        usage = data.get("usageMetadata") or {}
        parsed = _parse_json(content)
        return AIProviderResponse(
            content=json.dumps(parsed, ensure_ascii=False),
            data=parsed,
            input_tokens=int(usage.get("promptTokenCount") or 0),
            output_tokens=int(usage.get("candidatesTokenCount") or 0),
            provider=self.provider_name,
            model_id=self.model_id,
            latency_ms=int((time.monotonic() - started) * 1000),
        )


def create_ai_provider(provider_name: str, *, model_id: str, timeout_seconds: float) -> AIProvider:
    normalized = (provider_name or "bedrock").strip().lower().replace("-", "_")
    if normalized in {"bedrock", "aws_bedrock"}:
        return BedrockAIProvider(model_id=model_id)
    if normalized == "openai":
        return OpenAICompatibleProvider(
            provider_name="openai",
            model_id=model_id,
            api_key=_required_env("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
            timeout_seconds=timeout_seconds,
        )
    if normalized in {"azure", "azure_openai"}:
        return OpenAICompatibleProvider(
            provider_name="azure_openai",
            model_id=model_id,
            api_key=_required_env("AZURE_OPENAI_API_KEY"),
            base_url=_required_env("AZURE_OPENAI_API_BASE_URL"),
            timeout_seconds=timeout_seconds,
        )
    if normalized == "deepseek":
        return OpenAICompatibleProvider(
            provider_name="deepseek",
            model_id=model_id,
            api_key=_required_env("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com/v1"),
            timeout_seconds=timeout_seconds,
        )
    if normalized in {"claude", "anthropic"}:
        return AnthropicProvider(
            model_id=model_id,
            api_key=_required_env("ANTHROPIC_API_KEY"),
            timeout_seconds=timeout_seconds,
        )
    if normalized in {"google", "gemini"}:
        return GeminiProvider(
            model_id=model_id,
            api_key=_required_env("GOOGLE_API_KEY"),
            timeout_seconds=timeout_seconds,
        )
    raise AIServiceError(f"Unsupported AI provider: {provider_name}", category="PROVIDER_UNAVAILABLE")


async def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("AI provider HTTP error: %s", exc)
        raise AIServiceError("AI provider rejected the request.", category="PROVIDER_REJECTED") from exc
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("AI provider network error: %s", exc)
        raise AIServiceError("AI provider is unavailable.", category="PROVIDER_UNAVAILABLE") from exc
    except ValueError as exc:
        raise AIServiceError("AI provider returned invalid JSON.", category="BAD_PROVIDER_RESPONSE") from exc


def _parse_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AIServiceError("AI provider returned invalid JSON.", category="INVALID_JSON") from exc
    if not isinstance(parsed, dict):
        raise AIServiceError("AI provider returned non-object JSON.", category="INVALID_JSON_SHAPE")
    return parsed


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value and value.strip():
        return value.strip()
    raise AIServiceError(f"{name} is required for the selected AI provider.", category="PROVIDER_UNAVAILABLE")
