"""PDF rasterization for receipt attachments.

Uses PyMuPDF (AGPL-3.0 — a deliberate copyleft choice for this project).
Receipts are effectively single-page documents; only the first page is
rendered for thumbnails and AI extraction.
"""

from __future__ import annotations

PDF_MAGIC = b"%PDF-"


def is_pdf(data: bytes) -> bool:
    return data[:5] == PDF_MAGIC


def render_pdf_first_page(data: bytes, dpi: int = 200) -> bytes:
    """First page of a PDF as PNG bytes. Raises ValueError on empty or
    unparseable documents."""
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not open PDF: {exc}") from exc
    try:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        pixmap = doc[0].get_pixmap(dpi=dpi)
        return pixmap.tobytes("png")
    finally:
        doc.close()
