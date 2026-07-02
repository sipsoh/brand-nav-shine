"""LLM provider behind an interface (SETUP.md §23.2).

Services depend on the `LLMClient` protocol; the OpenAI implementation is
resolved only when an API key is configured. Keyless environments get `None`
and callers fall back to deterministic behavior.
"""

import json
import logging
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        """Return a JSON object conforming to `schema`. Raises on failure."""
        ...


class LLMUnavailable(Exception):
    pass


class OpenAILLMClient:
    def __init__(self, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = model

    def complete_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        last_error: Exception | None = None
        for _ in range(MAX_ATTEMPTS):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                    },
                )
                content = response.choices[0].message.content
                return json.loads(content)
            except Exception as error:  # transient API/parse errors: retry once
                last_error = error
        raise LLMUnavailable(str(last_error))


def _configured() -> bool:
    return bool(settings.openai_api_key) and settings.openai_api_key != "replace_me"


def get_semantic_mapper_llm() -> LLMClient | None:
    return OpenAILLMClient(model=settings.openai_model_text_analysis) if _configured() else None


def get_planner_llm() -> LLMClient | None:
    return OpenAILLMClient(model=settings.openai_model_planner) if _configured() else None
