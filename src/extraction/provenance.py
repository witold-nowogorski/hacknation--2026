"""Provenance of extracted values: which rule or LLM task produced each value, and from where in the text."""

from dataclasses import dataclass
from typing import Any, Literal

Source = Literal["rule", "llm", "derived", "default"]
SNIPPET_MARGIN = 50  # characters of context on each side of a value


@dataclass(frozen=True, slots=True)
class Found:
    """A normalised value as found by the engine, with its position in the document text."""

    value: Any
    source: Source
    detail: str  # the rule (label, pattern, class), LLM task or lookup that produced it
    span: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class ValueSource:
    """Where one output value came from, for the trace of a document."""

    path: str  # with list positions, e.g. "pelnomocnicy[1].imie_nazwisko"
    value: Any
    source: Source
    detail: str
    page: int | None
    snippet: str | None


@dataclass(frozen=True, slots=True)
class Extraction:
    """A document's output JSON and the provenance of every value in it."""

    data: dict[str, Any]
    sources: tuple[ValueSource, ...] = ()
