from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.core.config import settings

T = TypeVar("T", bound=BaseModel)


class LlmNotConfigured(RuntimeError):
    pass


class LlmOutputError(RuntimeError):
    pass


class StructuredParser(Protocol):
    """Turns a system+user prompt into a Pydantic model. Never talks to the ledger."""

    def parse(self, *, system: str, user: str, response_model: type[T]) -> T: ...


class OpenAIStructuredParser:
    """OpenAI (or compatible) structured output. Draft generator only."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise LlmNotConfigured(
                "OPENAI_API_KEY is required when CLAIM_COMPILER_MODE or INCIDENT_LINKER_MODE is llm"
            )
        from openai import OpenAI

        kwargs: dict[str, str] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self._client = OpenAI(**kwargs)
        self._model = settings.openai_model

    def parse(self, *, system: str, user: str, response_model: type[T]) -> T:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            completion = self._client.beta.chat.completions.parse(
                model=self._model,
                messages=messages,
                response_format=response_model,
                temperature=0,
            )
        except AttributeError:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = completion.choices[0].message.content
            if not content:
                raise LlmOutputError("model returned empty JSON")
            return response_model.model_validate_json(content)
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise LlmOutputError("model returned an empty structured payload")
        return parsed
