"""Filesystem locations of the application, defined once in run.py and passed down."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Workspace:
    """All paths the application reads from or writes to."""

    root: Path  # repository root (git metadata for reports)
    input_dir: Path  # <case>/*.pdf to process
    output_dir: Path  # <case>/<file>.json results (scored)
    doc_types_dir: Path  # config/doc_types/<name>/doc_type.toml
    models_dir: Path  # Docling models
    cache_dir: Path  # cached Docling conversions and LLM responses
    runs_dir: Path  # artifacts of each evaluation run (git-ignored)
    reports_dir: Path  # evaluation reports (committed)
