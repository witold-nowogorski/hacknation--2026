"""Evaluation reports: what was run, with which config, and how it scored; plus their history.

Reports are committed (eval/reports/), so scores of every variant stay comparable over time.
Only runs on the same document set (`dataset_id`) are ranked against each other.
"""

import hashlib
import logging
import subprocess
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from src.evaluation.evaluator import NO_TYPE, EvalScores
from src.pipeline.documents import InputDocument

logger = logging.getLogger(__name__)

LEADERBOARD_SIZE = 10


class RunInfo(BaseModel):
    """When, on what and with which code an experiment was evaluated."""

    run_id: str  # "<timestamp>_<experiment>", also the report file name
    experiment: str
    pipeline: str  # pipeline class name
    started_at: datetime
    duration_s: float
    documents: int
    seconds_per_document: float
    dataset_id: str
    git_commit: str | None
    git_dirty: bool | None


class EvalReport(BaseModel):
    """Run info, snapshots of everything configurable (pipeline config, document types) and the scores."""

    run: RunInfo
    config: dict[str, Any]
    doc_types: dict[str, Any] = {}  # config/doc_types/* as loaded: keyword tuning changes results too
    scores: EvalScores


def dataset_id(documents: Sequence[InputDocument]) -> str:
    """Short fingerprint of the evaluated document set."""
    labels = "\n".join(sorted(document.label for document in documents))
    return hashlib.sha256(labels.encode("utf-8")).hexdigest()[:12]


def git_revision(repo_dir: Path) -> tuple[str | None, bool | None]:
    """Current commit and whether the working tree has uncommitted changes; (None, None) without git."""
    try:
        commit = _git(repo_dir, "rev-parse", "--short", "HEAD")
        dirty = bool(_git(repo_dir, "status", "--porcelain", "--untracked-files=no"))
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None, None
    return commit, dirty


def _git(repo_dir: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True, check=True)
    return completed.stdout.strip()


class ReportStore:
    """Evaluation reports as `<directory>/<run id>.json`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def save(self, report: EvalReport) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{report.run.run_id}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self) -> list[EvalReport]:
        """All readable reports, oldest first; reports in an outdated format are skipped with a warning."""
        reports = []
        for path in sorted(self._directory.glob("*.json")):
            try:
                reports.append(EvalReport.model_validate_json(path.read_text(encoding="utf-8")))
            except ValidationError:
                logger.warning("Skipping report in an outdated format: %s", path.name)
        return sorted(reports, key=lambda report: report.run.started_at)


def format_leaderboard(reports: Sequence[EvalReport], current: EvalReport) -> str:
    """Ranking of runs on the current run's document set, best strict F1 first."""
    comparable = [report for report in reports if report.run.dataset_id == current.run.dataset_id]
    ranked = sorted(comparable, key=lambda r: (-r.scores.strict.f1, -r.scores.classification.accuracy))
    doc_types = [label for label in current.scores.by_doc_type if label != NO_TYPE]

    header = f"  {'#':>3}  {'experiment':24s} {'F1':>6} {'F1 norm':>7} " + " ".join(
        f"{label[:12]:>12}" for label in doc_types) + f" {'class.':>6}  started"
    lines = [f"Leaderboard ({current.run.documents} documents, dataset {current.run.dataset_id}, strict F1):", header]
    for rank, report in enumerate(ranked, start=1):
        if rank <= LEADERBOARD_SIZE or report.run.run_id == current.run.run_id:
            lines.append(_leaderboard_row(rank, report, doc_types, is_current=report.run.run_id == current.run.run_id))

    previous = [report for report in ranked if report.run.run_id != current.run.run_id]
    if previous:
        best = previous[0]
        delta = current.scores.strict.f1 - best.scores.strict.f1
        lines.append(f"  Δ F1 vs previous best ({best.run.experiment}, {best.run.run_id}): {delta:+.3f}")
    return "\n".join(lines)


def _leaderboard_row(rank: int, report: EvalReport, doc_types: list[str], is_current: bool) -> str:
    scores = report.scores
    per_type = " ".join(
        f"{scores.by_doc_type[label].f1:12.3f}" if label in scores.by_doc_type else f"{'-':>12}" for label in doc_types
    )
    marker = "  ← this run" if is_current else ""
    return (f"  {rank:>3}  {report.run.experiment[:24]:24s} {scores.strict.f1:6.3f} {scores.normalised.f1:7.3f} "
            f"{per_type} {scores.classification.accuracy:6.3f}  {report.run.started_at:%Y-%m-%d %H:%M}{marker}")
