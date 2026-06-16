"""LLM provider interfaces and adapters."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider cannot complete a request."""


class LLMResponse(BaseModel):
    """Normalized response returned by all LLM providers."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    text: str
    usage: dict[str, int] = Field(default_factory=dict)
    raw: Any | None = None

    def json_object(self) -> dict[str, Any]:
        """Parse the response text as a JSON object."""
        parsed = parse_json_response(self.text)
        if not isinstance(parsed, dict):
            raise LLMProviderError("Expected a JSON object from LLM response")
        return parsed

    def json_array(self) -> list[Any]:
        """Parse the response text as a JSON array."""
        parsed = parse_json_response(self.text)
        if not isinstance(parsed, list):
            raise LLMProviderError("Expected a JSON array from LLM response")
        return parsed


class LLMProvider(Protocol):
    """Shared provider interface."""

    provider_name: str
    model: str

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        """Generate text for a prompt."""


def parse_json_response(text: str) -> Any:
    """Parse JSON from common LLM response shapes.

    Handles plain JSON and fenced Markdown blocks. The function intentionally
    returns any JSON type so callers can decide whether they need an object,
    array, string, or scalar.
    """
    candidate = text.strip()
    candidate = re.sub(r"^```(?:json)?\s*\n?", "", candidate)
    candidate = re.sub(r"\n?```\s*$", "", candidate).strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    array_match = re.search(r"\[[\s\S]*\]", candidate)
    if array_match:
        return json.loads(array_match.group())

    object_match = re.search(r"\{[\s\S]*\}", candidate)
    if object_match:
        return json.loads(object_match.group())

    raise LLMProviderError(f"Could not parse JSON from response: {text[:160]}")


class MockLLMProvider:
    """Deterministic local provider for tests and demos."""

    provider_name = "mock"

    def __init__(
        self,
        *,
        model: str = "mock-local",
        default_response: str = "{}",
        responses: dict[str, str] | None = None,
    ):
        self.model = model
        self.default_response = default_response
        self.responses = responses or {}
        self.calls: list[dict[str, str | None]] = []

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        """Return a deterministic response without network calls."""
        self.calls.append({"prompt": prompt, "system": system})
        text = self.responses.get(prompt, self.default_response)
        return LLMResponse(
            provider=self.provider_name,
            model=self.model,
            text=text,
            usage={"input_chars": len(prompt), "output_chars": len(text)},
        )


class FallbackLLMProvider:
    """Try a primary provider, then a backup provider on failure."""

    provider_name = "fallback"

    def __init__(self, primary: LLMProvider, backup: LLMProvider):
        self.primary = primary
        self.backup = backup
        self.model = f"{primary.model}->{backup.model}"

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        """Generate with primary provider and fall back to backup if needed."""
        try:
            return self.primary.generate(prompt, system=system)
        except Exception as primary_error:
            try:
                response = self.backup.generate(prompt, system=system)
            except Exception as backup_error:
                raise LLMProviderError(
                    f"primary and backup providers failed: {primary_error}; {backup_error}"
                ) from backup_error

            response.usage["fallback_used"] = 1
            response.usage["primary_error_chars"] = len(str(primary_error))
            return response


class OpenAIProvider:
    """OpenAI Responses API adapter.

    The SDK import is lazy so optional dependencies are not required for tests.
    """

    provider_name = "openai"

    def __init__(
        self,
        *,
        model: str | None = DEFAULT_OPENAI_MODEL,
        api_key: str | None = None,
    ):
        self.model = model or os.getenv("OPENAI_MODEL")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        """Generate text with OpenAI."""
        if not self.api_key:
            raise LLMProviderError("OPENAI_API_KEY is required for OpenAIProvider")
        if not self.model:
            raise LLMProviderError("OPENAI_MODEL or an explicit model is required for OpenAIProvider")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMProviderError(
                "OpenAIProvider requires the optional dependency: pip install -e '.[openai]'"
            ) from exc

        client = OpenAI(api_key=self.api_key)
        input_payload: str | list[dict[str, str]]
        if system:
            input_payload = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]
        else:
            input_payload = prompt

        response = client.responses.create(model=self.model, input=input_payload)
        text = getattr(response, "output_text", "") or ""
        usage_obj = getattr(response, "usage", None)
        usage = {}
        if usage_obj:
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                value = getattr(usage_obj, key, None)
                if value is not None:
                    usage[key] = int(value)

        return LLMResponse(
            provider=self.provider_name,
            model=self.model,
            text=text,
            usage=usage,
            raw=response,
        )


class GeminiProvider:
    """Google Gemini adapter retained for compatibility with the original agents."""

    provider_name = "gemini"

    def __init__(
        self,
        *,
        model: str | None = DEFAULT_GEMINI_MODEL,
        api_key: str | None = None,
    ):
        self.model = model or os.getenv("GEMINI_MODEL")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        """Generate text with Gemini."""
        if not self.api_key:
            raise LLMProviderError("GEMINI_API_KEY is required for GeminiProvider")
        if not self.model:
            raise LLMProviderError("GEMINI_MODEL or an explicit model is required for GeminiProvider")

        try:
            from google import genai
        except ImportError as exc:
            raise LLMProviderError(
                "GeminiProvider requires the optional dependency: pip install -e '.[gemini]'"
            ) from exc

        client = genai.Client(api_key=self.api_key)
        contents = prompt if not system else f"{system}\n\n{prompt}"
        response = client.models.generate_content(model=self.model, contents=contents)
        text = response.text or ""

        return LLMResponse(
            provider=self.provider_name,
            model=self.model,
            text=text,
            usage={"input_chars": len(contents), "output_chars": len(text)},
            raw=response,
        )
