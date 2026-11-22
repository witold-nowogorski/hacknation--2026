"""Text extraction stage: the interface used by pipelines and its cached Docling implementation."""

import logging
from abc import ABC, abstractmethod
from functools import cached_property
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from docling.document_converter import DocumentConverter

from src.cache import DiskCache
from src.text_extraction.docling_models import use_local_models
from src.text_extraction.extractor import Conversion, build_converter, convert, to_extracted_document
from src.text_extraction.models import ConversionSettings, ExtractedDocument

logger = logging.getLogger(__name__)

# Part of the cache key: bump it when the cached Conversion changes shape, so old entries are ignored.
CONVERSION_FORMAT = 2


class TextExtractor(ABC):
    """Turns a PDF into text blocks."""

    @abstractmethod
    def extract(self, pdf_path: Path) -> ExtractedDocument: ...


class DoclingTextExtractor(TextExtractor):
    """Docling conversion cached per (PDF content, conversion settings, Docling version).

    The converter is built on the first cache miss only, so a fully cached run never loads
    the models. Failed conversions are not cached: they may be transient (e.g. a timeout).
    """

    def __init__(self, settings: ConversionSettings, models_dir: Path, cache: DiskCache) -> None:
        self._settings = settings
        self._models_dir = models_dir
        self._cache = cache
        self._settings_key = f"{settings.model_dump_json()}|docling {version('docling')}|format {CONVERSION_FORMAT}"

    def extract(self, pdf_path: Path) -> ExtractedDocument:
        key = DiskCache.key(pdf_path.read_bytes(), self._settings_key)
        cached = self._cache.get(key)
        if cached is not None:
            conversion = Conversion.model_validate_json(cached)
        else:
            conversion = convert(self._converter, pdf_path, self._settings.max_pages)
            if conversion.ok:
                self._cache.put(key, conversion.model_dump_json())
        return to_extracted_document(pdf_path, conversion)

    @cached_property
    def _converter(self) -> DocumentConverter:
        logger.info("Loading Docling models from %s", self._models_dir)
        start = perf_counter()
        use_local_models(self._models_dir)
        converter = build_converter(self._settings)
        logger.info("Docling models loaded in %.1f s (once per run)", perf_counter() - start)
        return converter
