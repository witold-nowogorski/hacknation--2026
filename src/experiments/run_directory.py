"""Artifacts of one evaluation run, kept for error analysis (git-ignored).

<runs_dir>/<run id>/
  run.log           full log of the run
  output/           the pipeline's JSON for every document
  traces/           per document: conversion, classification scores and the source of every value
  documents.jsonl   one record per document: types, time, counts
  errors.jsonl      one record per wrong field: expected vs predicted
  report.json       same report as in eval/reports/
"""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Self

from src.evaluation.evaluator import DocumentEvaluation
from src.experiments.reports import EvalReport
from src.pipeline.documents import DocumentResult, write_result, write_trace

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class RunDirectory:
    """Writes the artifacts of one evaluation run."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def create(cls, runs_dir: Path, base_id: str) -> Self:
        """Create `<runs_dir>/<base_id>`, adding `-2`, `-3`, ... if runs start within the same second."""
        runs_dir.mkdir(parents=True, exist_ok=True)
        path, suffix = runs_dir / base_id, 1
        while True:
            try:
                path.mkdir()
                return cls(path)
            except FileExistsError:
                suffix += 1
                path = runs_dir / f"{base_id}-{suffix}"

    @property
    def run_id(self) -> str:
        return self.path.name

    @contextmanager
    def capture_log(self) -> Iterator[None]:
        """Copy all log records emitted inside the block to `run.log`."""
        handler = logging.FileHandler(self.path / "run.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            yield
        finally:
            root_logger.removeHandler(handler)
            handler.close()

    def record(self, result: DocumentResult, evaluation: DocumentEvaluation, eval_set: str) -> None:
        """Save the document's output JSON and append its records."""
        write_result(result, self.path / "output")
        write_trace(result, self.path / "traces")
        self._append("documents.jsonl", [{
            "eval_set": eval_set,
            "document": result.document.label,
            "expected_type": evaluation.expected_type,
            "predicted_type": result.doc_type,
            "type_correct": evaluation.type_correct,
            "elapsed_s": round(result.elapsed_s, 3),
            "conversion_s": result.extracted.conversion_s if result.extracted else None,
            "pages": result.extracted.page_count if result.extracted else None,
            "values_in_text": evaluation.coverage.present,
            "values_checked": evaluation.coverage.total,
            "tp": evaluation.strict.tp,
            "fp": evaluation.strict.fp,
            "fn": evaluation.strict.fn,
            "error": result.error,
        }])
        self._append("errors.jsonl", [asdict(error) for error in evaluation.errors])

    def write_report(self, report: EvalReport) -> None:
        (self.path / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _append(self, file_name: str, records: list[dict[str, Any]]) -> None:
        with (self.path / file_name).open("a", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
