"""Entry point. Settings and experiments are defined here in code instead of command-line arguments.

Run from the repo root:  python -m src.run
  MODE = "run"   process WORKSPACE.input_dir into WORKSPACE.output_dir with RUN_EXPERIMENT
  MODE = "eval"  evaluate EVAL_EXPERIMENTS on the training set; reports go to eval/reports/,
                 full artifacts of each run to traces/runs/<run id>/
"""

import logging
from pathlib import Path
from typing import Literal

from src.experiments.experiment import Experiment, select_experiments
from src.experiments.runner import ExperimentRunner
from src.pipeline.config import PipelineConfig
from src.pipeline.documents import find_documents, write_result
from src.pipeline.null_pipeline import NullPipeline
from src.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]

# --- Settings ---------------------------------------------------------------
MODE: Literal["run", "eval"] = "run"
RUN_EXPERIMENT = "null-baseline"  # pipeline used in MODE = "run"
EVAL_EXPERIMENTS = ["null-baseline"]  # evaluated in this order in MODE = "eval"
EVAL_CASES: list[str] | None = None  # e.g. ["przyklad_01", "negatywne"] for a quick run; None = all
LOG_LEVEL = logging.INFO

WORKSPACE = Workspace(
    root=ROOT,
    input_dir=ROOT / "dane" / "input",
    output_dir=ROOT / "dane" / "output",
    eval_data_dir=ROOT / "dane",
    models_dir=ROOT / "models",
    cache_dir=ROOT / ".cache",
    runs_dir=ROOT / "traces" / "runs",
    reports_dir=ROOT / "eval" / "reports",
)

# --- Experiments ------------------------------------------------------------
EXPERIMENTS = [
    Experiment(NullPipeline, PipelineConfig(
        name="null-baseline",
        description="Recognises nothing: F1 floor and smoke test of the evaluation loop.",
    )),
]
# ----------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def configure_logging(level: int) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")


def process_input(experiment: Experiment, workspace: Workspace) -> None:
    """Production run: one JSON per input PDF."""
    documents = find_documents(workspace.input_dir)
    logger.info("Processing %d documents from %s with %s", len(documents), workspace.input_dir, experiment.name)
    pipeline = experiment.build_pipeline(workspace)
    for index, result in enumerate(pipeline.run(documents), start=1):
        write_result(result, workspace.output_dir)
        logger.info("[%d/%d] %s -> %s (%.2f s)", index, len(documents), result.document.label,
                    result.doc_type or "none", result.elapsed_s)


def main() -> None:
    configure_logging(LOG_LEVEL)
    match MODE:
        case "run":
            [experiment] = select_experiments(EXPERIMENTS, [RUN_EXPERIMENT])
            process_input(experiment, WORKSPACE)
        case "eval":
            ExperimentRunner(WORKSPACE, EVAL_CASES).run_all(select_experiments(EXPERIMENTS, EVAL_EXPERIMENTS))
        case _:
            raise SystemExit(f"Unknown MODE: {MODE!r}")


if __name__ == "__main__":
    main()
