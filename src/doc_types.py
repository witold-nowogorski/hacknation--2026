"""Document type definitions: `config/doc_types/<name>/doc_type.toml`, validated on load.

Everything specific to a document type lives in its folder; adding a type needs no code.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

CONFIG_FILE = "doc_type.toml"


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


def load_doc_types(directory: Path) -> dict[str, DocTypeConfig]:
    """All document types under `directory`, by name; invalid configs fail loudly with their path."""
    doc_types = {}
    for path in sorted(directory.glob(f"*/{CONFIG_FILE}")):
        with path.open("rb") as file:
            content = tomllib.load(file)
        try:
            doc_types[path.parent.name] = DocTypeConfig(name=path.parent.name, **content)
        except ValidationError as error:
            raise ValueError(f"Invalid document type config {path}:\n{error}") from error
    if not doc_types:
        raise ValueError(f"No document types found in {directory} (expected */{CONFIG_FILE})")
    return doc_types
