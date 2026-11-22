"""HTTP API: process PDFs with a pipeline from src/run.py and return the output JSON with provenance.

Start from the repo root:  python -m uvicorn src.api:app --port 8000
Swagger UI: /docs, ReDoc: /redoc, OpenAPI schema: /openapi.json.
Uploads are processed in a temporary folder; nothing is written to the output folder.
"""

import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from src.experiments.experiment import select_experiments
from src.extraction.provenance import ValueSource
from src.pipeline.documents import DocumentResult, InputDocument
from src.pipeline.pipeline import Pipeline
from src.run import ENV_FILE, EXPERIMENTS, LOG_LEVEL, RUN_EXPERIMENT, WORKSPACE, configure_logging, load_env_file


class ExperimentInfo(BaseModel):
    """A pipeline variant the API can run."""

    name: str
    description: str
    llm_model: str | None  # None = rules only
    default: bool


class DocumentOutput(BaseModel):
    """The result for one uploaded PDF."""

    file_name: str
    doc_type: str | None  # None = not one of the document types; `data` is then {}
    data: dict[str, Any]  # the output JSON, as written in run mode
    elapsed_s: float
    error: str | None  # set when the PDF could not be processed
    classification_scores: dict[str, float]
    sources: list[ValueSource]  # where every value of `data` came from


class ProcessResponse(BaseModel):
    experiment: str
    documents: list[DocumentOutput]


class _Pipelines:
    """One pipeline per experiment, built on first use (Docling models load once).

    Processing holds a lock: the converter and the LLM client are not thread-safe, and the work
    is CPU-bound, so documents are processed one at a time.
    """

    def __init__(self) -> None:
        self._pipelines: dict[str, Pipeline] = {}
        self.lock = Lock()

    def get(self, name: str) -> Pipeline:
        if name not in self._pipelines:
            [experiment] = select_experiments(EXPERIMENTS, [name])
            self._pipelines[name] = experiment.build_pipeline(WORKSPACE)
        return self._pipelines[name]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(LOG_LEVEL)
    load_env_file(ENV_FILE)
    yield


app = FastAPI(
    title="Odwołania2json API",
    description="Odwołanie, pełnomocnictwo lub potwierdzenie przelewu (PDF) → JSON. Inne dokumenty dają `{}`.",
    lifespan=lifespan,
)
pipelines = _Pipelines()


@app.get("/health")
def health() -> dict[str, str]:
    """The server is up."""
    return {"status": "ok"}


@app.get("/experiments")
def experiments() -> list[ExperimentInfo]:
    """Pipeline variants that /documents can run."""
    return [ExperimentInfo(name=experiment.name, description=experiment.config.description,
                           llm_model=experiment.config.llm.model if experiment.config.llm else None,
                           default=experiment.name == RUN_EXPERIMENT)
            for experiment in EXPERIMENTS]


@app.post("/documents")
def process_documents(
    files: Annotated[list[UploadFile], File(description="PDF files")],
    experiment: Annotated[str, Query(description="Pipeline variant, see /experiments")] = RUN_EXPERIMENT,
) -> ProcessResponse:
    """Classify each PDF and extract its fields; results come in upload order."""
    if experiment not in {known.name for known in EXPERIMENTS}:
        raise HTTPException(404, f"Unknown experiment {experiment!r}; see /experiments")
    not_pdf = [file.filename for file in files if not (file.filename or "").lower().endswith(".pdf")]
    if not_pdf:
        raise HTTPException(400, f"Only PDF files are accepted: {not_pdf}")

    with tempfile.TemporaryDirectory() as folder, pipelines.lock:
        documents = []
        for index, file in enumerate(files):  # one folder per upload, so equal file names do not collide
            path = Path(folder) / str(index) / Path(file.filename or "document.pdf").name
            path.parent.mkdir()
            path.write_bytes(file.file.read())
            documents.append(InputDocument(case=str(index), path=path))
        results = list(pipelines.get(experiment).run(documents))
    return ProcessResponse(experiment=experiment, documents=[_output(result) for result in results])


def _output(result: DocumentResult) -> DocumentOutput:
    return DocumentOutput(file_name=result.document.path.name, doc_type=result.doc_type, data=result.data,
                          elapsed_s=round(result.elapsed_s, 3), error=result.error,
                          classification_scores=result.scores, sources=list(result.sources))
