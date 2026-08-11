import base64

import pytest

from igab.services.ai_service import prepare_image_for_model
from igab.utils.pdf import is_pdf, render_pdf_first_page


def make_pdf(pages: int = 1) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}: TOTAL $42.50")
    data = doc.tobytes()
    doc.close()
    return data


class TestPdfUtils:
    def test_is_pdf_detects_magic(self):
        assert is_pdf(make_pdf()) is True
        assert is_pdf(b"\x89PNG\r\n") is False
        assert is_pdf(b"") is False

    def test_render_first_page_returns_png(self):
        png = render_pdf_first_page(make_pdf(pages=3))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_garbage_pdf_raises_value_error(self):
        with pytest.raises(ValueError):
            render_pdf_first_page(b"%PDF-1.4 not really a pdf")


class TestPrepareImageWithPdf:
    def test_pdf_is_rasterized_to_jpeg_base64(self):
        b64 = prepare_image_for_model(make_pdf())
        decoded = base64.b64decode(b64)
        assert decoded[:3] == b"\xff\xd8\xff"  # JPEG magic

    def test_plain_image_still_works(self):
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (32, 32), "white").save(buf, "PNG")
        b64 = prepare_image_for_model(buf.getvalue())
        assert base64.b64decode(b64)[:3] == b"\xff\xd8\xff"
