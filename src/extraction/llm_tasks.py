"""LLM tasks of a document type (`[[llm_tasks]]` in doc_type.toml): focused questions after the rules.

The LLM never makes a value worse: a failed call or an unusable answer leaves the rule values,
written values must occur in the context the LLM saw, rewritten names must keep every word's
stem, and coded values are limited to their value type's choices by the answer schema.
"""

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, create_model

from src.doc_types import DocTypeConfig, LlmTaskRule, leaf_paths
from src.inference.llm_client import LlmClient, LlmError
from src.value_types import VALUE_TYPES, ValueType, fold

logger = logging.getLogger(__name__)

Span = tuple[int, int]  # a section's start and end in the text
STEM_LETTERS = 3  # "Jana" -> "Jan", "Pawła" -> "Paweł": the first letters stay
WHITESPACE = re.compile(r"\s+")


class _Names(BaseModel):
    names: list[str]


class _Task:
    """One compiled task with its answer schema."""

    def __init__(self, rule: LlmTaskRule, value_types: dict[str, str]) -> None:
        self.rule = rule
        self.when = [re.compile(regex, re.IGNORECASE | re.MULTILINE) for regex in rule.when]
        self.types = {path: VALUE_TYPES[value_types[path]] for path in rule.fields}
        self.keys = _answer_keys(rule.fields)
        self.schema = create_model(
            rule.name.title().replace("_", ""),
            **{self.keys[path]: (_answer_type(value_type), ...) for path, value_type in self.types.items()},
        ) if rule.kind == "extract" else _Names

    def triggered(self, text: str) -> bool:
        """Contexts are matched folded (like rules), names as written (case endings need diacritics)."""
        searched = fold(text) if self.rule.kind == "extract" else text
        return not self.when or any(regex.search(searched) for regex in self.when)


class LlmTasks:
    """Runs a document type's LLM tasks over the values its rules found."""

    def __init__(self, doc_type: DocTypeConfig, client: LlmClient) -> None:
        value_types = leaf_paths(doc_type.output_schema)
        self._tasks = [_Task(rule, value_types) for rule in doc_type.llm_tasks]
        self._client = client

    def apply(self, text: str, spans: dict[str, Span | None], values: dict[str, list[Any]]) -> None:
        """Update `values` in place with the tasks' accepted answers."""
        for task in self._tasks:
            try:
                if task.rule.kind == "extract":
                    self._extract(task, text, spans, values)
                else:
                    self._nominative(task, values)
            except LlmError as error:
                logger.warning("LLM task %s failed, rule values kept: %s", task.rule.name, error)

    def _extract(self, task: _Task, text: str, spans: dict[str, Span | None], values: dict[str, list[Any]]) -> None:
        asked = [path for path in task.rule.fields if task.rule.mode == "decide" or not values.get(path)]
        context = _context(task.rule, text, spans)
        if not asked or not context or not task.triggered(context):
            return
        answer = self._client.complete_json(f"{task.rule.prompt}\n\nFragment dokumentu:\n{context}", task.schema)
        for path in asked:
            value_type = task.types[path]
            value = value_type.normalize(getattr(answer, task.keys[path]))
            if value is not None and (not value_type.written or _occurs(value, value_type, context)):
                values[path] = [value]

    def _nominative(self, task: _Task, values: dict[str, list[Any]]) -> None:
        names = [(path, index, name) for path in task.rule.fields for index, name in enumerate(values.get(path, []))]
        if not names or not task.triggered("\n".join(name for _, _, name in names)):
            return
        answer = self._client.complete_json(
            f"{task.rule.prompt}\n\n{[name for _, _, name in names]}", task.schema)
        if len(answer.names) != len(names):
            logger.warning("LLM task %s returned %d names for %d", task.rule.name, len(answer.names), len(names))
            return
        for (path, index, original), rewritten in zip(names, answer.names):
            value = VALUE_TYPES["person_name"].normalize(rewritten)
            if value is not None and _same_stems(original, value):
                values[path][index] = value


def _answer_keys(paths: list[str]) -> dict[str, str]:
    """JSON keys of the answer: the last path segment, or the whole path when segments repeat."""
    last = [path.split(".")[-1].replace("-", "_") for path in paths]
    return {path: key if last.count(key) == 1 else re.sub(r"\W+", "_", path).strip("_")
            for path, key in zip(paths, last)}


def _answer_type(value_type: ValueType) -> Any:
    allowed = Literal[value_type.choices] if value_type.choices else value_type.python_type  # type: ignore[valid-type]
    return allowed | None


def _context(rule: LlmTaskRule, text: str, spans: dict[str, Span | None]) -> str:
    """The first listed section that exists (like field rules), else the document start; at most context_chars."""
    if not rule.sections:
        return text[:rule.context_chars]
    span = next((spans[name] for name in rule.sections if spans[name]), None)
    return text[span[0]:span[1]].strip()[:rule.context_chars] if span else ""


def _occurs(value: Any, value_type: ValueType, context: str) -> bool:
    """A written value is among the context's candidates of its type, or (free text) appears in it."""
    if value_type.pattern:
        candidates = {value_type.normalize(match.group()) for match in re.finditer(value_type.pattern, context)}
        if value in candidates:
            return True
    return _compact(str(value)) in _compact(context)


def _same_stems(original: str, rewritten: str) -> bool:
    before, after = fold(original).split(), fold(rewritten).split()
    return len(before) == len(after) and all(a[:STEM_LETTERS] == b[:STEM_LETTERS] for a, b in zip(before, after))


def _compact(text: str) -> str:
    return WHITESPACE.sub("", fold(text))
