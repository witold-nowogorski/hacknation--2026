"""Reference JSON for a training document: `dane/<case>/<stem>.json`, or `{}` for negatives."""

import json
from dataclasses import dataclass
from typing import Any

from src.pipeline.documents import InputDocument

# Folder of documents that must not be recognised as any type.
NEGATIVES_CASE = "negatywne"
# Training PDFs whose reference file has a different stem.
REFERENCE_STEMS = {"potwierdzenie_przelewu": "przelew"}


@dataclass(frozen=True, slots=True)
class Reference:
    """Expected document type (None = negative) and expected JSON."""

    doc_type: str | None
    data: dict[str, Any]


def load_reference(document: InputDocument) -> Reference:
    """Load the reference for a training document; the file stem names the document type."""
    if document.case == NEGATIVES_CASE:
        return Reference(doc_type=None, data={})
    stem = REFERENCE_STEMS.get(document.path.stem, document.path.stem)
    path = document.path.with_name(f"{stem}.json")
    return Reference(doc_type=stem, data=json.loads(path.read_text(encoding="utf-8")))
