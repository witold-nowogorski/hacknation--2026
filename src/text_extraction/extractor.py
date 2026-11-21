"""PDF -> ExtractedDocument with Docling.

Pipeline choice (CPU benchmark on dane/): standard pipeline with layout analysis,
TableFormer in FAST mode (needed: bank transfers are two-column label/value tables and
signature blocks become tables) and RapidOCR in Polish only where a page has no usable
text layer. Full-page OCR and the VLM pipeline were slower and less accurate.
"""

import logging
from pathlib import Path

from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ContentLayer, DocItem, DoclingDocument, TableItem, TextItem

from src.text_extraction.models import BBox, ConversionSettings, ExtractedDocument, TextBlock, sort_reading_order

logger = logging.getLogger(__name__)

# Page headers/footers are kept: dates and places of the letter sometimes land there.
CONTENT_LAYERS = {ContentLayer.BODY, ContentLayer.FURNITURE}

_STATUS_NAMES = {
    ConversionStatus.SUCCESS: "success",
    ConversionStatus.PARTIAL_SUCCESS: "partial_success",
}


def build_converter(settings: ConversionSettings) -> DocumentConverter:
    """Create a CPU-only converter; build once and reuse (model loading is slow)."""
    options = PdfPipelineOptions(
        do_ocr=True,
        # Engine set explicitly: the "auto" default picks different engines per OS.
        ocr_options=RapidOcrOptions(lang=list(settings.ocr_lang), replace_broken_text_layer=True),
        do_table_structure=True,
        document_timeout=settings.document_timeout_s,
        accelerator_options=AcceleratorOptions(num_threads=settings.num_threads, device="cpu"),
    )
    options.table_structure_options.mode = TableFormerMode(settings.table_mode)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def extract_document(converter: DocumentConverter, pdf_path: Path, max_pages: int) -> ExtractedDocument:
    """Convert the first max_pages pages of a PDF; unreadable files yield status "failure"."""
    result = converter.convert(pdf_path, raises_on_error=False, page_range=(1, max_pages))
    errors = tuple(error.error_message for error in result.errors)
    if errors:
        logger.warning("Docling reported errors for %s: %s", pdf_path, errors)

    blocks: list[TextBlock] = []
    if result.document is not None and result.status != ConversionStatus.FAILURE:
        blocks = [block for item, _ in result.document.iterate_items(
            included_content_layers=CONTENT_LAYERS, traverse_pictures=True,
        ) if (block := _to_block(item, result.document))]

    return ExtractedDocument(
        source=pdf_path,
        blocks=tuple(sort_reading_order(blocks)),
        page_count=result.input.page_count or 0,
        status=_STATUS_NAMES.get(result.status, "failure"),
        errors=errors,
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
