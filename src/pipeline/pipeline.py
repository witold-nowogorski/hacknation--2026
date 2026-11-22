"""Abstract pipeline: turns input documents into results, one document at a time."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import replace
from time import perf_counter
from typing import Self

from src.inference.llm_client import LlmUsage
from src.pipeline.config import PipelineConfig
from src.pipeline.documents import DocumentResult, InputDocument
from src.workspace import Workspace

logger = logging.getLogger(__name__)


class DocumentProcessingError(Exception):
    """A single document could not be processed; the batch continues with `{}` for it."""


class Pipeline(ABC):
    """Base class of pipeline variants.

    Subclasses assemble themselves from a config (`from_config`) and process one document
    (`process`). Timing and the per-document error policy live in `run`.
    """

    @classmethod
    @abstractmethod
    def from_config(cls, config: PipelineConfig, workspace: Workspace) -> Self:
        """Build the pipeline and its stages from the experiment config."""

    @property
    def llm_usage(self) -> LlmUsage | None:
        """LLM calls and tokens spent so far; None for pipelines without an LLM."""
        return None

    @abstractmethod
    def process(self, document: InputDocument) -> DocumentResult:
        """Classify and extract one document; raise DocumentProcessingError if it is unreadable."""

    def run(self, documents: Sequence[InputDocument]) -> Iterator[DocumentResult]:
        """Yield one timed result per document, in order.

        A DocumentProcessingError yields `{}` and the batch continues; any other exception
        is a bug and stops the run.
        """
        for document in documents:
            start = perf_counter()
            try:
                result = self.process(document)
            except DocumentProcessingError as error:
                logger.exception("Failed to process %s", document.label)
                result = DocumentResult.empty(document, error=str(error))
            yield replace(result, elapsed_s=perf_counter() - start)
