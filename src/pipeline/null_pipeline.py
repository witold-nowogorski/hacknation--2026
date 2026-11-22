"""Null baseline: recognises nothing. Gives the F1 floor and smoke-tests the eval loop."""

from typing import Self

from src.pipeline.config import PipelineConfig
from src.pipeline.documents import DocumentResult, InputDocument
from src.pipeline.pipeline import Pipeline
from src.workspace import Workspace


class NullPipeline(Pipeline):
    """Returns `{}` for every document."""

    @classmethod
    def from_config(cls, config: PipelineConfig, workspace: Workspace) -> Self:
        return cls()

    def process(self, document: InputDocument) -> DocumentResult:
        return DocumentResult.empty(document)
