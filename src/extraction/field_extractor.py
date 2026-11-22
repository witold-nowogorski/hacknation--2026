"""Field extraction stage interface: the output JSON of a classified document."""

from abc import ABC, abstractmethod

from src.doc_types import DocTypeConfig
from src.extraction.provenance import Extraction
from src.text_extraction.models import ExtractedDocument


class FieldExtractor(ABC):
    """Builds the output JSON of a document of a known type, with the provenance of its values."""

    @abstractmethod
    def extract(self, document: ExtractedDocument, doc_type: DocTypeConfig) -> Extraction: ...
