"""Staged pipeline: text extraction -> classification -> field extraction, with injected stages."""

import logging
from collections.abc import Mapping
from typing import Self

from src.cache import DiskCache
from src.classification.classifier import Classifier
from src.classification.keyword_classifier import KeywordClassifier
from src.doc_types import DocTypeConfig, load_doc_types
from src.extraction.field_extractor import FieldExtractor
from src.extraction.rule_extractor import RuleExtractor
from src.inference.llm_client import LlmClient, LlmUsage
from src.pipeline.config import PipelineConfig
from src.pipeline.documents import DocumentResult, InputDocument
from src.pipeline.pipeline import DocumentProcessingError, Pipeline
from src.text_extraction.text_extractor import DoclingTextExtractor, TextExtractor
from src.workspace import Workspace

logger = logging.getLogger(__name__)


class StagedPipeline(Pipeline):
    """Runs the three stages in order; which implementation each stage uses comes from the config."""

    def __init__(self, text_extractor: TextExtractor, classifier: Classifier, field_extractor: FieldExtractor,
                 doc_types: Mapping[str, DocTypeConfig], llm: LlmClient | None = None) -> None:
        self._text_extractor = text_extractor
        self._classifier = classifier
        self._field_extractor = field_extractor
        self._doc_types = doc_types
        self._llm = llm

    @classmethod
    def from_config(cls, config: PipelineConfig, workspace: Workspace) -> Self:
        doc_types = load_doc_types(workspace.doc_types_dir)
        llm = LlmClient(config.llm, DiskCache(workspace.cache_dir / "llm")) if config.llm else None
        return cls(
            text_extractor=DoclingTextExtractor(
                config.conversion, workspace.models_dir, DiskCache(workspace.cache_dir / "docling")),
            classifier=KeywordClassifier(doc_types, config.classification),
            field_extractor=RuleExtractor(doc_types, llm),
            doc_types=doc_types,
            llm=llm,
        )

    @property
    def llm_usage(self) -> LlmUsage | None:
        return self._llm.usage if self._llm else None

    def process(self, document: InputDocument) -> DocumentResult:
        extracted = self._text_extractor.extract(document.path)
        if not extracted.ok:
            reason = "; ".join(extracted.errors) or "no text found"
            raise DocumentProcessingError(f"text extraction {extracted.status}: {reason}")

        classification = self._classifier.classify(extracted)
        logger.debug("%s -> %s, scores %s", document.label, classification.doc_type, classification.scores)
        if classification.doc_type is None:
            return DocumentResult(document=document, doc_type=None, data={}, extracted=extracted)

        data = self._field_extractor.extract(extracted, self._doc_types[classification.doc_type])
        return DocumentResult(document=document, doc_type=classification.doc_type, data=data, extracted=extracted)
