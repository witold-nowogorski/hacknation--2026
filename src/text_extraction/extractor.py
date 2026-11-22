"""PDF -> Conversion (Docling's document) -> ExtractedDocument (our text blocks).

Pipeline choice (CPU benchmarks on dane/, see docs/architecture.md): standard pipeline with
layout analysis, TableFormer (bank transfers are two-column label/value tables, signature
blocks become tables) and RapidOCR in Polish only where a page has no usable text layer, on
the first pages only. Full-page OCR and the VLM pipeline were slower and less accurate.
"""

import logging
from pathlib import Path
from time import perf_counter
from typing import Literal

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ContentLayer, DocItem, DoclingDocument, TableItem, TextItem
from pydantic import BaseModel

from src.text_extraction.models import BBox, ConversionSettings, ExtractedDocument, TextBlock, sort_reading_order

logger = logging.getLogger(__name__)

# Page headers/footers are kept: dates and places of the letter sometimes land there.
CONTENT_LAYERS = {ContentLayer.BODY, ContentLayer.FURNITURE}

_STATUS_NAMES = {
    ConversionStatus.SUCCESS: "success",
    ConversionStatus.PARTIAL_SUCCESS: "partial_success",
}


def build_converter(settings: ConversionSettings) -> DocumentConverter:
    """Create a CPU-only converter with its models loaded; build once and reuse (loading is slow)."""
    tables = settings.table_mode != "none"
    options = PdfPipelineOptions(
        do_ocr=True,
        # Engine set explicitly: the "auto" default picks different engines per OS.
        ocr_options=RapidOcrOptions(lang=list(settings.ocr_lang), replace_broken_text_layer=True),
        do_table_structure=tables,
        document_timeout=settings.document_timeout_s,
        accelerator_options=AcceleratorOptions(num_threads=settings.num_threads, device="cpu"),
    )
    if tables:
        options.table_structure_options.mode = TableFormerMode(settings.table_mode)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    converter.initialize_pipeline(InputFormat.PDF)  # load now, not inside the first document's conversion time
    return converter


class Conversion(BaseModel):
    """Docling's own result for one PDF. This is what gets cached: converting is the slow step,
    and keeping Docling's document lets our block mapping change without re-converting."""

    status: Literal["success", "partial_success", "failure"]
    page_count: int
    seconds: float  # wall time of the conversion; cached with it, so reports always show the cold-run cost
    errors: tuple[str, ...] = ()
    document: DoclingDocument | None = None

    @property
    def ok(self) -> bool:
        return self.status != "failure" and self.document is not None


def convert(converter: DocumentConverter, pdf_path: Path, max_pages: int) -> Conversion:
    """Convert the first max_pages pages of a PDF; unreadable files yield status "failure"."""
    start = perf_counter()
    result = converter.convert(pdf_path, raises_on_error=False, page_range=(1, max_pages))
    seconds = perf_counter() - start
    errors = tuple(error.error_message for error in result.errors)
    if errors:
        logger.warning("Docling reported errors for %s: %s", pdf_path, errors)
    status = _STATUS_NAMES.get(result.status, "failure")
    return Conversion(
        status=status,
        page_count=result.input.page_count or 0,
        seconds=round(seconds, 3),
        errors=errors,
        document=result.document if status != "failure" else None,
    )


def to_extracted_document(pdf_path: Path, conversion: Conversion) -> ExtractedDocument:
    """Text blocks of a converted PDF in reading order."""
    blocks: list[TextBlock] = []
    if conversion.document is not None:
        blocks = [block for item, _ in conversion.document.iterate_items(
            included_content_layers=CONTENT_LAYERS, traverse_pictures=True,
        ) if (block := _to_block(item, conversion.document))]

    return ExtractedDocument(
        source=pdf_path,
        blocks=tuple(sort_reading_order(blocks)),
        page_count=conversion.page_count,
        status=conversion.status,
        conversion_s=conversion.seconds,
        errors=conversion.errors,
    )


def _to_block(item: DocItem, document: DoclingDocument) -> TextBlock | None:
    """Map a Docling text or table item to a TextBlock; None for empty/other items."""
    match item:
        case TableItem():
            rows = tuple(tuple(cell.text for cell in row) for row in item.data.grid)
            rows = tuple(row for row in rows if any(cell.strip() for cell in row))
            if not rows:
                return None
            text, table_rows = "", rows
        case TextItem() if item.text.strip():
            text, table_rows = item.text.strip(), ()
        case _:
            return None

    page, bbox = 0, None
    if item.prov:
        provenance = item.prov[0]
        page = provenance.page_no
        page_height = document.pages[page].size.height
        box = provenance.bbox.to_top_left_origin(page_height)
        bbox = BBox(left=box.l, top=box.t, right=box.r, bottom=box.b)

    return TextBlock(
        text=text, label=item.label.value, page=page, bbox=bbox,
        layer=item.content_layer.value, table_rows=table_rows,
    )
