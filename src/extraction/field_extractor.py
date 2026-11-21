"""Field extraction stage interface: the output JSON of a classified document."""

from abc import ABC, abstractmethod
from typing import Any

from src.doc_types import DocTypeConfig
from src.text_extraction.models import ExtractedDocument


class FieldExtractor(ABC):
    """Builds the output JSON of a document of a known type."""

    @abstractmethod
    def extract(self, document: ExtractedDocument, doc_type: DocTypeConfig) -> dict[str, Any]: ...


class EmptyFieldExtractor(FieldExtractor):
    """Extracts nothing: isolates classification quality until real extractors exist."""

    def extract(self, document: ExtractedDocument, doc_type: DocTypeConfig) -> dict[str, Any]:
        return {}
