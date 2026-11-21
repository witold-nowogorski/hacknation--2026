"""Documents flowing through a pipeline: input PDFs and their JSON results."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class InputDocument:
    """One input PDF: `<input>/<case>/<file>.pdf`."""

    case: str
    path: Path

    @property
    def label(self) -> str:
        """`<case>/<file>.pdf`, for logs and records."""
        return f"{self.case}/{self.path.name}"


@dataclass(frozen=True, slots=True)
class DocumentResult:
    """Pipeline output for one document; `data` is the JSON to write (`{}` = not recognised)."""

    document: InputDocument
    doc_type: str | None
    data: dict[str, Any]
    elapsed_s: float = 0.0
    error: str | None = None  # set when processing failed and `{}` was written instead

    @classmethod
    def empty(cls, document: InputDocument, error: str | None = None) -> Self:
        """Result of an unrecognised (or failed) document."""
        return cls(document=document, doc_type=None, data={}, error=error)


def find_documents(input_dir: Path) -> list[InputDocument]:
    """All `<input_dir>/<case>/*.pdf` files, sorted for deterministic runs."""
    return [InputDocument(case=path.parent.name, path=path) for path in sorted(input_dir.glob("*/*.pdf"))]


def write_result(result: DocumentResult, output_dir: Path) -> Path:
    """Write `<output_dir>/<case>/<pdf stem>.json` and return its path."""
    target = output_dir / result.document.case / f"{result.document.path.stem}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
