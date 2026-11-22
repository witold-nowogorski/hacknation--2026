"""Evaluation sets: named groups of documents whose references sit next to the PDFs."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from src.pipeline.documents import InputDocument, find_documents


@dataclass(frozen=True, slots=True)
class EvalSet:
    """`root.glob(pattern)`; scores are reported per set, so e.g. scans are visible on their own."""

    name: str
    root: Path
    pattern: str


@dataclass(frozen=True, slots=True)
class EvalDocument:
    """A document to evaluate and the set it belongs to."""

    eval_set: str
    document: InputDocument


def select_documents(eval_sets: Sequence[EvalSet], cases: Sequence[str] | None = None) -> list[EvalDocument]:
    """Documents of all sets, optionally only the given cases; fails if the selection is empty."""
    selected = [
        EvalDocument(eval_set=eval_set.name, document=document)
        for eval_set in eval_sets
        for document in find_documents(eval_set.root, eval_set.pattern)
        if cases is None or document.case in cases
    ]
    if not selected:
        raise ValueError(f"No documents found in {[s.name for s in eval_sets]} for cases {cases}")
    return selected
