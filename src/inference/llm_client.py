"""LLM inference over an OpenAI-compatible chat API, with a response cache and token accounting.

Responses are cached by the full request (model, messages, schema, generation settings), so
evaluation runs are reproducible and repeated runs cost no tokens. Each cache entry keeps the
request next to the answer, which makes every LLM-derived value traceable to its prompt.
The API key is read from the environment (`.env`), never from config or code.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI, OpenAIError
from openai.types import CompletionUsage
from pydantic import BaseModel, ConfigDict, ValidationError

from src.cache import DiskCache

logger = logging.getLogger(__name__)


class LlmSettings(BaseModel):
    """Endpoint, model and generation settings of one LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str
    model: str
    api_key_env: str = "LLM_API_KEY"
    temperature: float = 0.0  # deterministic answers
    max_tokens: int = 1024
    timeout_s: float = 60.0
    max_retries: int = 2


class LlmError(Exception):
    """The LLM call failed or its answer is unusable."""


@dataclass(slots=True)
class LlmUsage:
    """Calls and tokens spent by one client (cache hits cost nothing)."""

    calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LlmClient:
    """Chat completions with optional JSON-schema-constrained answers."""

    def __init__(self, settings: LlmSettings, cache: DiskCache) -> None:
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise ValueError(f"Environment variable {settings.api_key_env} is not set (add it to .env)")
        self._settings = settings
        self._cache = cache
        self._client = OpenAI(base_url=settings.base_url, api_key=api_key,
                              timeout=settings.timeout_s, max_retries=settings.max_retries)
        self.usage = LlmUsage()

    def complete(self, prompt: str, system: str | None = None) -> str:
        """Free-text answer to a prompt."""
        return self._chat(prompt, system, response_format=None)

    def complete_json[Response: BaseModel](self, prompt: str, schema: type[Response],
                                           system: str | None = None) -> Response:
        """Answer constrained to the schema of a Pydantic model and validated against it."""
        response_format = {"type": "json_schema", "json_schema": {
            "name": schema.__name__, "schema": schema.model_json_schema(), "strict": True,
        }}
        content = self._chat(prompt, system, response_format)
        try:
            return schema.model_validate_json(content)
        except ValidationError as error:
            raise LlmError(f"{self._settings.model} answer does not match {schema.__name__}: {error}") from error

    def _chat(self, prompt: str, system: str | None, response_format: dict[str, Any] | None) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        request: dict[str, Any] = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
        }
        if response_format:
            request["response_format"] = response_format

        key = DiskCache.key(self._settings.base_url, json.dumps(request, ensure_ascii=False, sort_keys=True))
        if (cached := self._cache.get(key)) is not None:
            self.usage.cache_hits += 1
            return json.loads(cached)["answer"]

        try:
            response = self._client.chat.completions.create(**request)
        except OpenAIError as error:
            raise LlmError(f"{self._settings.model} request failed: {error}") from error
        answer = response.choices[0].message.content
        if not answer:
            raise LlmError(f"{self._settings.model} returned an empty answer")

        self._record_usage(response.usage)
        self._cache.put(key, json.dumps({"request": request, "answer": answer}, ensure_ascii=False, indent=1))
        return answer

    def _record_usage(self, usage: CompletionUsage | None) -> None:
        self.usage.calls += 1
        if usage is not None:
            self.usage.prompt_tokens += usage.prompt_tokens
            self.usage.completion_tokens += usage.completion_tokens
        logger.debug("LLM call %d to %s, tokens so far: %d prompt, %d completion", self.usage.calls,
                     self._settings.model, self.usage.prompt_tokens, self.usage.completion_tokens)
