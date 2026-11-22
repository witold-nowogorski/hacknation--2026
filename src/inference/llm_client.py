"""LLM inference over an OpenAI-compatible chat API, with a response cache and token accounting.

Responses are cached by the full request (model, messages, schema, generation settings), so
evaluation runs are reproducible and repeated runs cost no tokens. Only answers that pass
validation are cached, and cached answers are validated again when read. Each cache entry keeps
the request, the answer, its token usage and latency, so every LLM-derived value is traceable to
its prompt and reports show the cost of a cold run even when the cache is warm.
The API key is read from the environment (`.env`), never from config or code.
"""

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ConfigDict, ValidationError

from src.cache import DiskCache

logger = logging.getLogger(__name__)

# Small models drift into runaway whitespace inside JSON unless told to keep it on one line.
COMPACT_JSON = "Zwróć zwarty JSON w jednej linii."


class LlmSettings(BaseModel):
    """Endpoint, model and generation settings of one LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str
    model: str
    api_key_env: str = "LLM_API_KEY"
    temperature: float = 0.0  # deterministic answers
    max_tokens: int = 200  # answers are small; a runaway answer fails fast instead of burning tokens
    timeout_s: float = 20.0
    max_retries: int = 1  # transport retries (connection errors, 5xx)
    max_consecutive_failures: int = 3  # then the endpoint counts as down for the rest of the run (rules only)


class LlmError(Exception):
    """The LLM call failed or its answer is unusable."""


@dataclass(slots=True)
class LlmUsage:
    """Calls and their cost: tokens and seconds count cached answers too, as a cold run would spend them."""

    calls: int = 0  # requests sent to the API
    cache_hits: int = 0
    failures: int = 0  # unusable answers after a retry
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0


class LlmClient:
    """Chat completions with JSON-schema-constrained, validated answers."""

    def __init__(self, settings: LlmSettings, cache: DiskCache) -> None:
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise ValueError(f"Environment variable {settings.api_key_env} is not set (add it to .env)")
        self._settings = settings
        self._cache = cache
        self._client = OpenAI(base_url=settings.base_url, api_key=api_key,
                              timeout=settings.timeout_s, max_retries=settings.max_retries)
        self.usage = LlmUsage()
        self._failures_in_a_row = 0

    def complete_json[Response: BaseModel](self, prompt: str, schema: type[Response],
                                           system: str | None = None) -> Response:
        """Answer constrained to the schema of a Pydantic model and validated against it.

        An invalid answer is retried once; a second invalid answer raises LlmError.
        """
        response_format = {"type": "json_schema", "json_schema": {
            "name": schema.__name__, "schema": schema.model_json_schema(), "strict": True,
        }}
        system = f"{system}\n{COMPACT_JSON}" if system else COMPACT_JSON
        for attempt in range(2):
            answer = self._chat(prompt, system, response_format, schema.model_validate_json, attempt)
            if answer is not None:
                return schema.model_validate_json(answer)
        self.usage.failures += 1
        raise LlmError(f"{self._settings.model} gave no valid {schema.__name__} after a retry")

    def _chat(self, prompt: str, system: str, response_format: dict[str, Any],
              validate: Callable[[str], Any], attempt: int) -> str | None:
        """A valid answer from the cache or the API; None if the API answer fails validation."""
        request: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
            "response_format": response_format,
        }
        if attempt:  # the same request again would give the same answer at temperature 0
            request["seed"] = attempt
        key = DiskCache.key(self._settings.base_url, json.dumps(request, ensure_ascii=False, sort_keys=True))
        if (cached := self._cache.get(key)) is not None:
            entry = json.loads(cached)
            if _is_valid(entry["answer"], validate):
                self._count(entry)
                self.usage.cache_hits += 1
                return entry["answer"]

        if self._failures_in_a_row >= self._settings.max_consecutive_failures:
            raise LlmError(f"{self._settings.model} is unavailable ({self._failures_in_a_row} failed requests in a row)")
        start = perf_counter()
        try:
            response = self._client.chat.completions.create(**request)
        except OpenAIError as error:
            self._failures_in_a_row += 1
            raise LlmError(f"{self._settings.model} request failed: {error}") from error
        self._failures_in_a_row = 0
        answer = response.choices[0].message.content or ""
        usage = response.usage
        entry = {"request": request, "answer": answer, "seconds": round(perf_counter() - start, 3),
                 "prompt_tokens": usage.prompt_tokens if usage else 0,
                 "completion_tokens": usage.completion_tokens if usage else 0}
        self.usage.calls += 1
        self._count(entry)
        if not _is_valid(answer, validate):
            logger.warning("%s answer failed validation (attempt %d): %.200s", self._settings.model, attempt + 1, answer)
            return None
        self._cache.put(key, json.dumps(entry, ensure_ascii=False, indent=1))
        return answer

    def _count(self, entry: dict[str, Any]) -> None:
        self.usage.prompt_tokens += entry.get("prompt_tokens", 0)
        self.usage.completion_tokens += entry.get("completion_tokens", 0)
        self.usage.seconds = round(self.usage.seconds + entry.get("seconds", 0.0), 3)


def _is_valid(answer: str, validate: Callable[[str], Any]) -> bool:
    try:
        validate(answer)
    except ValidationError:
        return False
    return True
