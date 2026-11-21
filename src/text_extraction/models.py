"""Settings and result types of text extraction, independent of Docling."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Blocks whose tops differ by at most this many PDF points are on the same line.
LINE_TOLERANCE_PT = 3.0


class ConversionSettings(BaseModel):
    """Docling conversion parameters; defaults are the CPU benchmark winners (see extractor)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The brief says key data sits on the first three pages; one extra page of margin.
    max_pages: int = 4
    document_timeout_s: float = 120.0
    ocr_lang: tuple[str, ...] = ("pl",)
    table_mode: Literal["fast", "accurate"] = "fast"
    num_threads: int = 4


@dataclass(frozen=True, slots=True)
class BBox:
    """Bounding box in PDF points, top-left origin (y grows downwards)."""

    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True, slots=True)
class TextBlock:
    """One layout element (paragraph, heading, list item or table) with provenance."""

    text: str
    label: str  # Docling label, e.g. "text", "section_header", "page_header", "table"
    page: int  # 1-based
    bbox: BBox | None
    layer: str  # "body" or "furniture" (page headers/footers)
    table_rows: tuple[tuple[str, ...], ...] = ()

    @property
    def is_table(self) -> bool:
        return bool(self.table_rows)

    def render(self) -> str:
        """Plain text; table rows become 'cell | cell' lines."""
        if self.is_table:
            return "\n".join(" | ".join(cell.strip() for cell in row) for row in self.table_rows)
        return self.text


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """Text blocks of one PDF in reading order, plus conversion status."""

    source: Path
    blocks: tuple[TextBlock, ...]
    page_count: int
    status: Literal["success", "partial_success", "failure"]
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status != "failure" and bool(self.blocks)

    @property
    def text(self) -> str:
        return "\n".join(block.render() for block in self.blocks)

    @property
    def tables(self) -> list[TextBlock]:
        return [block for block in self.blocks if block.is_table]

    def lines(self) -> list[str]:
        """Non-empty, stripped text lines (handy for header heuristics)."""
        return [line.strip() for line in self.text.splitlines() if line.strip()]


def sort_reading_order(blocks: list[TextBlock]) -> list[TextBlock]:
    """Order blocks per page top-to-bottom, then left-to-right within a line.

    Docling's layout order sometimes moves spaced-out titles ("P E Ł N O M O C N I C T W O")
    and the "Miejscowość, dnia ..." header to the end of the page. Our documents are
    single-column, so geometry is the more reliable order. Blocks without a bounding box
    keep their relative order and go to the end of their page.
    """
    placed = sorted((b for b in blocks if b.bbox), key=lambda b: (b.page, b.bbox.top))
    lines: list[list[TextBlock]] = []
    for block in placed:
        current = lines[-1] if lines else None
        if current and block.page == current[0].page and block.bbox.top - current[0].bbox.top <= LINE_TOLERANCE_PT:
            current.append(block)
        else:
            lines.append([block])
    ordered = [block for line in lines for block in sorted(line, key=lambda b: b.bbox.left)]

    for block in (b for b in blocks if not b.bbox):
        position = sum(1 for other in ordered if other.page <= block.page)
        ordered.insert(position, block)
    return ordered
