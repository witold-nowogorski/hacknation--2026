"""Entry point. Settings and experiments are defined here in code instead of command-line arguments.

Run from the repo root:  python -m src.run
  MODE = "run"   process WORKSPACE.input_dir into WORKSPACE.output_dir with RUN_EXPERIMENT;
                 the source of every value goes to WORKSPACE.traces_dir
  MODE = "eval"  evaluate EVAL_EXPERIMENTS on EVAL_SETS; reports go to eval/reports/,
                 full artifacts of each run to traces/runs/<run id>/
"""

import logging
import os
from pathlib import Path
from typing import Literal

from src.classification.keyword_classifier import KeywordClassifierSettings
from src.experiments.eval_sets import EvalSet
from src.experiments.experiment import Experiment, select_experiments
from src.experiments.runner import ExperimentRunner
from src.inference.llm_client import LlmSettings
from src.pipeline.config import PipelineConfig
from src.pipeline.documents import find_documents, write_result, write_trace
from src.pipeline.null_pipeline import NullPipeline
from src.pipeline.staged_pipeline import StagedPipeline
from src.text_extraction.models import ConversionSettings
from src.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]

# --- Settings ---------------------------------------------------------------
MODE: Literal["run", "eval"] = "run"
RUN_EXPERIMENT = "hybrid-v1"  # pipeline used in MODE = "run"
EVAL_EXPERIMENTS = ["rules-v1", "hybrid-v1"]  # evaluated in this order in MODE = "eval"
EVAL_CASES: list[str] | None = None  # e.g. ["przyklad_01", "negatywne"] for a quick run; None = all
EVAL_SETS = [  # references sit next to the PDFs; a PDF without one must produce {}
    EvalSet("synthetic", ROOT / "dane", "przyklad_*/*.pdf"),  # text-layer cases, some with negatives inside
    EvalSet("negatives", ROOT / "dane", "negatywne/*.pdf"),
    EvalSet("scans", ROOT / "dane" / "skany", "*/*/*.pdf"),  # scanned documents: OCR path
]
LOG_LEVEL = logging.INFO
ENV_FILE = ROOT / ".env"  # secrets such as LLM_API_KEY; git-ignored

WORKSPACE = Workspace(
    root=ROOT,
    input_dir=ROOT / "dane" / "input",
    output_dir=ROOT / "dane" / "output",
    doc_types_dir=ROOT / "config" / "doc_types",
    models_dir=ROOT / "models",
    cache_dir=ROOT / ".cache",
    traces_dir=ROOT / "traces" / "production",
    runs_dir=ROOT / "traces" / "runs",
    reports_dir=ROOT / "eval" / "reports",
)

# --- LLM endpoints ----------------------------------------------------------
PSNC_URL = "https://llm.hpc.psnc.pl/v1"  # PSNC Poznań: EU-hosted, OpenAI-compatible, open-weight models
BIELIK_11B = LlmSettings(base_url=PSNC_URL, model="Bielik-11B-v3.0-Instruct")

# --- Experiments ------------------------------------------------------------
EXPERIMENTS = [
    Experiment(NullPipeline, PipelineConfig(
        name="null-baseline",
        description="Recognises nothing: F1 floor and smoke test of the evaluation loop.",
    )),
    Experiment(StagedPipeline, PipelineConfig(
        name="keywords-v1",
        description="Cached Docling text + keyword classifier from config/doc_types; no field extraction yet.",
    )),
    Experiment(StagedPipeline, PipelineConfig(
        name="keywords-2pages",
        description="keywords-v1, but keywords are searched on the first two pages (long appeal headers).",
        classification=KeywordClassifierSettings(pages=2),
    )),
    Experiment(StagedPipeline, PipelineConfig(
        name="tables-accurate",
        description="C1: first 2 pages, TableFormer ACCURATE: bank tables as intact 'label | value' rows.",
        conversion=ConversionSettings(table_mode="accurate"),
        classification=KeywordClassifierSettings(pages=2),
    )),
    Experiment(StagedPipeline, PipelineConfig(
        name="tables-none",
        description="C1: first 2 pages, no table structure: cells become text blocks; no TableFormer cost.",
        conversion=ConversionSettings(table_mode="none"),
        classification=KeywordClassifierSettings(pages=2),
    )),
    Experiment(StagedPipeline, PipelineConfig(
        name="rules-v1",
        description="C3: field rules from config/doc_types (labels, sections, value-type candidates); no LLM.",
        classification=KeywordClassifierSettings(pages=2),
    )),    Experiment(StagedPipeline, PipelineConfig(
        name="hybrid-v1",
        description="C4: rules-v1 plus the LLM tasks in config/doc_types (reason code, nominative names), Bielik-11B.",
        classification=KeywordClassifierSettings(pages=2),
        llm=BIELIK_11B,
    )),
]
# ----------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# Libraries that log every page or model load at INFO.
NOISY_LIBRARIES = ("docling", "docling_core", "RapidOCR", "rapidocr")


def configure_logging(level: int) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    for library in NOISY_LIBRARIES:
        logging.getLogger(library).setLevel(logging.WARNING)


def load_env_file(path: Path) -> None:
    """Put `KEY=value` lines of a .env file into the environment; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and not line.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def process_input(experiment: Experiment, workspace: Workspace) -> None:
    """Production run: one JSON per input PDF."""
    documents = find_documents(workspace.input_dir)
    logger.info("Processing %d documents from %s with %s", len(documents), workspace.input_dir, experiment.name)
    pipeline = experiment.build_pipeline(workspace)
    for index, result in enumerate(pipeline.run(documents), start=1):
        write_result(result, workspace.output_dir)
        write_trace(result, workspace.traces_dir)
        logger.info("[%d/%d] %s -> %s (%.2f s)", index, len(documents), result.document.label,
                    result.doc_type or "none", result.elapsed_s)


def main() -> None:
    configure_logging(LOG_LEVEL)
    load_env_file(ENV_FILE)
    match MODE:
        case "run":
            [experiment] = select_experiments(EXPERIMENTS, [RUN_EXPERIMENT])
            process_input(experiment, WORKSPACE)
        case "eval":
            ExperimentRunner(WORKSPACE, EVAL_SETS, EVAL_CASES).run_all(select_experiments(EXPERIMENTS, EVAL_EXPERIMENTS))
        case _:
            raise SystemExit(f"Unknown MODE: {MODE!r}")


if __name__ == "__main__":
    main()
