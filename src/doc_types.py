"""Document type definitions in `config/doc_types/<name>/`, validated on load.

  doc_type.toml   classification rules (later: field extraction rules)
  schema.json     the output JSON shape, with value-type names as leaves; one-element lists mean
                  "list of", e.g. {"przelew_bankowy": {"kwota": "amount", ...}}

Everything specific to a document type lives in its folder; adding a type needs no code.
"""

import json
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

CONFIG_FILE = "doc_type.toml"
SCHEMA_FILE = "schema.json"


class ClassificationRules(BaseModel):
    """Keyword evidence for this type; a negative weight is evidence against it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_score: float
    keywords: dict[str, float]


class DocTypeConfig(BaseModel):
    """One document type; `name` is the folder name and the type reported in results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    classification: ClassificationRules
    output_schema: dict[str, Any]

    @field_validator("output_schema")
    @classmethod
    def _check_output_schema(cls, schema: dict[str, Any]) -> dict[str, Any]:
        _check_template(schema, path="")
        return schema

    @property
    def output_keys(self) -> frozenset[str]:
        """Top-level keys of the output JSON; they identify the type of a reference JSON."""
        return frozenset(self.output_schema)


def _check_template(template: Any, path: str) -> None:
    """Objects are non-empty, lists hold exactly one element template, leaves are value-type names."""
    match template:
        case dict() if template:
            for key, value in template.items():
                _check_template(value, f"{path}.{key}" if path else key)
        case [element]:
            _check_template(element, f"{path}[]")
        case str():
            return
        case _:
            raise ValueError(f"{path or 'root'}: expected a non-empty object, a one-element list or a value-type name")


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
        except (OSError, tomllib.TOMLDecodeError, json.JSONDecodeError, ValidationError) as error:
            raise ValueError(f"Invalid document type config in {path.parent}:\n{error}") from error
    if not doc_types:
        raise ValueError(f"No document types found in {directory} (expected */{CONFIG_FILE})")
    return doc_types
