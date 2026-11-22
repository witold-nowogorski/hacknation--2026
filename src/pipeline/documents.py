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


def find_documents(root: Path, pattern: str = "*/*.pdf") -> list[InputDocument]:
    """PDFs matching `pattern` under `root`, sorted for deterministic runs.

    The case is the PDF's folder relative to `root` (`<case>` for `<input>/<case>/*.pdf`,
    `odwolania/0001` for nested layouts), so cases stay unique and outputs mirror the input tree.
    """
    return [InputDocument(case=path.parent.relative_to(root).as_posix(), path=path)
            for path in sorted(root.glob(pattern))]


def write_result(result: DocumentResult, output_dir: Path) -> Path:
    """Write `<output_dir>/<case>/<pdf stem>.json` and return its path."""
    target = output_dir / result.document.case / f"{result.document.path.stem}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
