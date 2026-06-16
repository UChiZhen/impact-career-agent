import pytest

from career_agent.llm import (
    LLMProviderError,
    LLMResponse,
    MockLLMProvider,
    OpenAIProvider,
    parse_json_response,
)


def test_mock_provider_returns_deterministic_response():
    provider = MockLLMProvider(
        default_response='{"fit_score": 84}',
        responses={"hello": '{"message": "world"}'},
    )

    response = provider.generate("hello", system="test system")

    assert response.provider == "mock"
    assert response.json_object() == {"message": "world"}
    assert provider.calls == [{"prompt": "hello", "system": "test system"}]


def test_parse_json_response_strips_markdown_fences():
    parsed = parse_json_response(
        """```json
        {"recommended_action": "apply_now"}
        ```"""
    )

    assert parsed == {"recommended_action": "apply_now"}


def test_parse_json_response_extracts_array():
    parsed = parse_json_response('Here is data: [{"title": "Analyst"}]')

    assert parsed == [{"title": "Analyst"}]


def test_llm_response_rejects_wrong_json_shape():
    response = LLMResponse(provider="mock", model="mock", text='["not", "object"]')

    with pytest.raises(LLMProviderError):
        response.json_object()


def test_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider()

    with pytest.raises(LLMProviderError, match="OPENAI_API_KEY"):
        provider.generate("hello")
