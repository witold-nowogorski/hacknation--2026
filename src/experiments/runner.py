"""Evaluation of experiments: run the pipeline on the training set, score, log, save artifacts and reports."""

import logging
from collections.abc import Sequence
from datetime import datetime
from time import perf_counter

from src.evaluation.evaluator import NO_TYPE, DocumentEvaluation, Evaluator, format_scores
from src.experiments.experiment import Experiment
from src.experiments.reports import EvalReport, ReportStore, RunInfo, dataset_id, format_leaderboard, git_revision
from src.experiments.run_directory import RunDirectory
from src.pipeline.documents import DocumentResult, InputDocument, find_documents
from src.workspace import Workspace

logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Evaluates experiments on `workspace.eval_data_dir`, optionally limited to some cases."""

    def __init__(self, workspace: Workspace, cases: Sequence[str] | None = None) -> None:
        self._workspace = workspace
        self._cases = cases
        self._reports = ReportStore(workspace.reports_dir)

    def run_all(self, experiments: Sequence[Experiment]) -> list[EvalReport]:
        return [self.run(experiment) for experiment in experiments]

    def run(self, experiment: Experiment) -> EvalReport:
        """Process and score every document, then save the report and log the leaderboard."""
        started_at = datetime.now().astimezone()
        run_directory = RunDirectory.create(self._workspace.runs_dir, f"{started_at:%Y%m%d-%H%M%S}_{experiment.name}")

        with run_directory.capture_log():
            documents = self._select_documents()
            logger.info("Experiment %s (%s): %d documents -> %s", experiment.name,
                        experiment.pipeline_class.__name__, len(documents), run_directory.path)
            pipeline = experiment.build_pipeline(self._workspace)
            evaluator = Evaluator()
            start = perf_counter()
            for index, result in enumerate(pipeline.run(documents), start=1):
                evaluation = evaluator.add(result)
                run_directory.record(result, evaluation)
                _log_progress(index, len(documents), result, evaluation, evaluator)

            report = self._build_report(experiment, run_directory.run_id, started_at, perf_counter() - start,
                                        documents, evaluator)
            run_directory.write_report(report)
            self._reports.save(report)
            logger.info("Done in %.1f s (%.2f s/document)\n%s", report.run.duration_s,
                        report.run.seconds_per_document, format_scores(report.scores))
            logger.info("%s", format_leaderboard(self._reports.load(), report))
        return report

    def _select_documents(self) -> list[InputDocument]:
        documents = find_documents(self._workspace.eval_data_dir)
        if self._cases is None:
            return documents
        selected = [document for document in documents if document.case in self._cases]
        if not selected:
            raise ValueError(f"No documents found for cases {list(self._cases)}")
        return selected

    def _build_report(self, experiment: Experiment, run_id: str, started_at: datetime, duration_s: float,
                      documents: list[InputDocument], evaluator: Evaluator) -> EvalReport:
        commit, dirty = git_revision(self._workspace.root)
        return EvalReport(
            run=RunInfo(
                run_id=run_id,
                experiment=experiment.name,
                pipeline=experiment.pipeline_class.__name__,
                started_at=started_at,
                duration_s=round(duration_s, 2),
                documents=len(documents),
                seconds_per_document=round(duration_s / len(documents), 3) if documents else 0.0,
                dataset_id=dataset_id(documents),
                git_commit=commit,
                git_dirty=dirty,
            ),
            config=experiment.config.model_dump(mode="json"),
            scores=evaluator.scores(),
        )


def _log_progress(index: int, total: int, result: DocumentResult, evaluation: DocumentEvaluation,
                  evaluator: Evaluator) -> None:
    """One line per document; misclassifications as warnings, failures as errors."""
    position = f"[{index:>{len(str(total))}}/{total}] {result.document.label:50s}"
    if result.error:
        logger.error("%s failed: %s", position, result.error)
        return

    predicted = result.doc_type or NO_TYPE
    verdict = "ok" if evaluation.type_correct else f"WRONG (expected {evaluation.expected_type or NO_TYPE})"
    counts = evaluation.strict
    document_f1 = f"{counts.f1:.2f}" if counts.tp + counts.fp + counts.fn else "-"
    running = evaluator.running
    level = logging.INFO if evaluation.type_correct else logging.WARNING
    logger.log(level, "%s %-15s %-5s F1 %4s %6.2f s | running F1 %.3f, class. %.3f", position, predicted, verdict,
               document_f1, result.elapsed_s, running.f1, evaluator.classification_accuracy)
