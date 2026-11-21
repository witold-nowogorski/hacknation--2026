"""Classification stage interface: which document type (if any) a document is."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.text_extraction.models import ExtractedDocument


@dataclass(frozen=True, slots=True)
class Classification:
    """Chosen type (None = not a known type) and the score of every type, for logs and traces."""

    doc_type: str | None
    scores: dict[str, float]


class Classifier(ABC):
    """Assigns a document type to an extracted document."""

    @abstractmethod
    def classify(self, document: ExtractedDocument) -> Classification: ...
