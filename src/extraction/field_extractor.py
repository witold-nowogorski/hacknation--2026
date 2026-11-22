"""Field extraction stage: the output JSON of a classified document."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from src.doc_types import DocTypeConfig
from src.extraction.output_model import OutputObject, build_output_model, skeleton
from src.text_extraction.models import ExtractedDocument


class FieldExtractor(ABC):
    """Builds the output JSON of a document of a known type."""

    @abstractmethod
    def extract(self, document: ExtractedDocument, doc_type: DocTypeConfig) -> dict[str, Any]: ...


class SkeletonExtractor(FieldExtractor):
    """The complete output structure with every value null; real extractors fill it in.

    Output models are built for all types up front, so an invalid schema fails when the pipeline
    is built, not on the first document of that type.
    """

    def __init__(self, doc_types: Mapping[str, DocTypeConfig]) -> None:
        self._models: dict[str, type[OutputObject]] = {
            name: build_output_model(doc_type) for name, doc_type in doc_types.items()}

    def extract(self, document: ExtractedDocument, doc_type: DocTypeConfig) -> dict[str, Any]:
        return self._models[doc_type.name].model_validate(skeleton(doc_type.output_schema)).model_dump()
