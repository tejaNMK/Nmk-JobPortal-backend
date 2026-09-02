from app.service.employer_service.ai_providers import (
    EmployerBedrockAIProvider,
    EmployerOpenAICompatibleProvider,
    create_employer_ai_provider,
)
from app.service.employer_service.ai_job_description_service import AIJobDescriptionService
from app.service.employer_service.ai_service import AIService


def test_employer_ai_service_prefers_employer_env(monkeypatch):
    monkeypatch.setenv("EMPLOYER_BEDROCK_MODEL_ID", "employer-model")
    monkeypatch.setenv("EMPLOYER_BEDROCK_REGION", "ap-south-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "shared-model")
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")

    service = AIService()

    assert service._model_id == "employer-model"
    assert service._region_name == "ap-south-1"


def test_employer_provider_factory_returns_employer_provider_classes(monkeypatch):
    monkeypatch.setenv("EMPLOYER_OPENAI_API_KEY", "employer-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "shared-test-key")
    monkeypatch.setenv("EMPLOYER_OPENAI_API_BASE_URL", "https://employer-openai.test/v1")

    bedrock = create_employer_ai_provider(
        "bedrock",
        model_id="bedrock-model",
        timeout_seconds=10,
    )
    openai = create_employer_ai_provider(
        "openai",
        model_id="openai-model",
        timeout_seconds=10,
    )

    assert isinstance(bedrock, EmployerBedrockAIProvider)
    assert isinstance(openai, EmployerOpenAICompatibleProvider)
    assert bedrock.__class__.__module__.startswith("app.service.employer_service.")
    assert openai.__class__.__module__.startswith("app.service.employer_service.")
    assert openai.api_key == "employer-test-key"
    assert openai.base_url == "https://employer-openai.test/v1"


def test_employer_provider_config_prefers_employer_env(monkeypatch):
    monkeypatch.setenv("EMPLOYER_AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_PROVIDER", "bedrock")
    monkeypatch.setenv("EMPLOYER_OPENAI_MODEL", "employer-openai-model")
    monkeypatch.setenv("OPENAI_MODEL", "shared-openai-model")
    monkeypatch.setenv("EMPLOYER_AI_JOB_DESCRIPTION_BEDROCK_MAX_TOKENS", "321")
    monkeypatch.setenv("AI_JOB_DESCRIPTION_BEDROCK_MAX_TOKENS", "123")

    config = AIJobDescriptionService._provider_config()

    assert config.provider == "openai"
    assert config.model == "employer-openai-model"
    assert config.max_tokens == 321
