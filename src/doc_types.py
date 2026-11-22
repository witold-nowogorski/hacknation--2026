"""Document type definitions in `config/doc_types/<name>/`, validated on load.

  doc_type.toml   classification rules, text sections, field extraction rules and LLM tasks
  schema.json     the output JSON shape, with value-type names as leaves; one-element lists mean
                  "list of", e.g. {"przelew_bankowy": {"kwota": "amount", ...}}

Everything specific to a document type lives in its folder; adding a type needs no code.
Regexes in rules are matched case-insensitively against text without Polish diacritics, so
they are written without diacritics (`odwolujac`, not `odwołując`).
"""

import json
import re
import tomllib
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from src.value_types import VALUE_TYPES

CONFIG_FILE = "doc_type.toml"
SCHEMA_FILE = "schema.json"


class ClassificationRules(BaseModel):
    """Keyword evidence for this type; a negative weight is evidence against it.

    `keywords` count anywhere in the searched pages, `head_keywords` only at the top of the document.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_score: float
    keywords: dict[str, float]
    head_keywords: dict[str, float] = {}


class SectionRule(BaseModel):
    """A part of the text that fields can be limited to, e.g. the block after "Odwołujący:"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: list[str] = []  # the section begins after the earliest match; empty = document start; no match = no section
    end: list[str] = []  # the section ends at the earliest match after its start
    max_chars: int | None = None


class LookupRule(BaseModel):
    """Value taken from a table, keyed by the value of an earlier field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    table: dict[str, str]


class FieldRule(BaseModel):
    """How one output field (a leaf path such as "Odwolujacy[].nip") is found.

    Exactly one way of reading applies, checked in this order:
      lookup     value from a table, keyed by an earlier field's value
      classify   the value whose regexes match earliest in the searched text, else `default`
      labels     the value follows one of the labels (tried in the listed order)
      (none)     the value is read from the start of the searched text
    The value itself is read by `pattern` if given (its first matching group), else as the first
    candidate of the field's value type (a date, an amount, a person's name, ...), else as free
    text up to the end of the line, continued on lines that start in lower case (wrapped text).
    `cut` regexes end the searched text early. Values of `exclude` fields are never taken.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sections: list[str] = []  # searched in this order until one yields a value; empty = whole text
    labels: list[str] = []
    pattern: str | None = None
    cut: list[str] = []
    skip: list[str] = []  # regexes removed at the start of a free-text value (a neighbouring label in a column layout)
    nth: int | None = None  # without a value after the labels: the n-th candidate (0-based) in the searched text
    window: int = 300  # characters read after a label
    # "segment": all values after the first matching label; "occurrences": all values after every label match
    multiple: Literal["no", "segment", "occurrences"] = "no"
    exclude: list[str] = []  # earlier fields whose values this one must not repeat
    classify: dict[str, list[str]] = {}
    default: str | None = None
    lookup: LookupRule | None = None
    only_if: dict[str, str] = {}  # read only when these earlier fields have these values

    @model_validator(mode="after")
    def _check_regexes(self) -> Self:
        for regex in [*self.labels, *self.cut, *self.skip, *(r for regexes in self.classify.values() for r in regexes),
                      *([self.pattern] if self.pattern else [])]:
            re.compile(regex)
        return self


class LlmTaskRule(BaseModel):
    """A focused LLM question about some fields, asked after the rules.

    kind "extract": the answer to `prompt` about a context (the first listed section that exists,
      else the document start); `mode` "decide" lets a valid answer replace the rule value, "fill" only fills empty
      fields. Values documents write out must occur in the context, or they are dropped.
    kind "nominative": the fields' person names rewritten in the nominative case; every word must
      keep its stem, or the original stays.
    The task runs only if a `when` regex matches: the folded context ("extract") or the names as
    written ("nominative"); empty = always.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: Literal["extract", "nominative"] = "extract"
    fields: list[str]
    sections: list[str] = []
    context_chars: int = 2000
    prompt: str
    mode: Literal["decide", "fill"] = "fill"
    when: list[str] = []

    @model_validator(mode="after")
    def _check_regexes(self) -> Self:
        for regex in self.when:
            re.compile(regex)
        return self


class DocTypeConfig(BaseModel):
    """One document type; `name` is the folder name and the type reported in results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    classification: ClassificationRules
    output_schema: dict[str, Any]
    sections: dict[str, SectionRule] = {}
    fields: dict[str, FieldRule] = {}
    llm_tasks: list[LlmTaskRule] = []

    @field_validator("output_schema")
    @classmethod
    def _check_output_schema(cls, schema: dict[str, Any]) -> dict[str, Any]:
        _check_template(schema, path="")
        return schema

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        """Field paths exist in the schema; sections exist; referenced fields come earlier."""
        leaves = leaf_paths(self.output_schema)
        earlier: list[str] = []
        for path, rule in self.fields.items():
            if path not in leaves:
                raise ValueError(f"fields.{path!r}: not a leaf of schema.json; leaves are {sorted(leaves)}")
            for section in rule.sections:
                if section not in self.sections:
                    raise ValueError(f"fields.{path!r}: unknown section {section!r}")
            for reference in [*rule.exclude, *rule.only_if, *([rule.lookup.source] if rule.lookup else [])]:
                if reference not in earlier:
                    raise ValueError(f"fields.{path!r}: {reference!r} must be a field defined earlier")
            earlier.append(path)
        for task in self.llm_tasks:
            for path in task.fields:
                if path not in leaves:
                    raise ValueError(f"llm_tasks {task.name!r}: {path!r} is not a leaf of schema.json")
                if task.kind == "nominative" and leaves[path] != "person_name":
                    raise ValueError(f"llm_tasks {task.name!r}: {path!r} is not a person_name")
            for section in task.sections:
                if section not in self.sections:
                    raise ValueError(f"llm_tasks {task.name!r}: unknown section {section!r}")
        return self

    @property
    def output_keys(self) -> frozenset[str]:
        """Top-level keys of the output JSON; they identify the type of a reference JSON."""
        return frozenset(self.output_schema)


def leaf_paths(template: Any, path: str = "") -> dict[str, str]:
    """Leaf path ("Odwolujacy[].nip") -> value type name."""
    match template:
        case dict():
            return {leaf: value_type for key, value in template.items()
                    for leaf, value_type in leaf_paths(value, f"{path}.{key}" if path else key).items()}
        case [element]:
            return leaf_paths(element, f"{path}[]")
        case _:
            return {path: template}


def _check_template(template: Any, path: str) -> None:
    """Objects are non-empty, lists hold exactly one element template, leaves name value types (src/value_types.py)."""
    match template:
        case dict() if template:
            for key, value in template.items():
                _check_template(value, f"{path}.{key}" if path else key)
        case [element]:
            _check_template(element, f"{path}[]")
        case str() if template in VALUE_TYPES:
            return
        case _:
            raise ValueError(f"{path or 'root'}: expected a non-empty object, a one-element list or one of the "
                             f"value types {sorted(VALUE_TYPES)}, got {template!r}")


def load_doc_types(directory: Path) -> dict[str, DocTypeConfig]:
    """All document types under `directory`, by name; invalid configs fail loudly with their path."""
    doc_types = {}
    for path in sorted(directory.glob(f"*/{CONFIG_FILE}")):
        schema_path = path.with_name(SCHEMA_FILE)
        try:
            with path.open("rb") as file:
                content = tomllib.load(file)
            output_schema = json.loads(schema_path.read_text(encoding="utf-8"))
            doc_types[path.parent.name] = DocTypeConfig(name=path.parent.name, output_schema=output_schema, **content)
        except (OSError, tomllib.TOMLDecodeError, json.JSONDecodeError, ValidationError, re.error) as error:
            raise ValueError(f"Invalid document type config in {path.parent}:\n{error}") from error
    if not doc_types:
        raise ValueError(f"No document types found in {directory} (expected */{CONFIG_FILE})")
    return doc_types
