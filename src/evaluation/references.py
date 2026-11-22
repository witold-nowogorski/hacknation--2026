"""Reference JSON of an evaluation document, and the document type it expects.

The reference is `<stem>.json` next to the PDF (or the JSON of a known renamed stem). A PDF
without one is a negative and must produce `{}`: the organiser places negatives both in
`negatywne/` and inside example cases. The expected type is recognised from the reference's
top-level keys, because file names say nothing reliable about content.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.doc_types import DocTypeConfig
from src.pipeline.documents import InputDocument

# Training PDFs whose reference file has a different stem (the organiser renames them over time).
REFERENCE_STEMS = {"potwierdzenie_przelewu": "przelew"}


@dataclass(frozen=True, slots=True)
class Reference:
    """Expected document type (None = negative) and expected JSON."""

    doc_type: str | None
    data: dict[str, Any]


class ReferenceLoader:
    """Finds and reads the reference of each evaluation document."""

    def __init__(self, doc_types: Mapping[str, DocTypeConfig]) -> None:
        self._types_by_keys = {doc_type.output_keys: name for name, doc_type in doc_types.items()}

    def load(self, document: InputDocument) -> Reference:
        path = reference_path(document.path)
        if path is None:
            return Reference(doc_type=None, data={})
        data = json.loads(path.read_text(encoding="utf-8"))
        doc_type = self._types_by_keys.get(frozenset(data))
        if data and doc_type is None:
            raise ValueError(f"{path}: top-level keys {sorted(data)} match no document type schema")
        return Reference(doc_type=doc_type, data=data)


def reference_path(pdf_path: Path) -> Path | None:
    """`<stem>.json` next to the PDF, else the JSON of its renamed stem; None if there is none."""
    for stem in (pdf_path.stem, REFERENCE_STEMS.get(pdf_path.stem)):
        if stem and (candidate := pdf_path.with_name(f"{stem}.json")).exists():
            return candidate
    return None
