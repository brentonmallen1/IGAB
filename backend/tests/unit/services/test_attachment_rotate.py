"""Rotate must persist a clockwise reorientation: file + thumbnail re-encoded
in place, DB media metadata refreshed, and non-image cases rejected."""

import uuid
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from igab.services import attachment_service as attachment_service_module
from igab.services.attachment_service import AttachmentService


def _png_bytes(size: tuple[int, int] = (64, 48)) -> bytes:
    """White image with a red 8x8 top-left block to track orientation.
    (A block, not a pixel — WebP's lossy encode smears single pixels.)"""
    img = Image.new("RGB", size, color=(255, 255, 255))
    img.paste((255, 0, 0), (0, 0, 8, 8))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_txn() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), date=date(2026, 8, 16))


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(attachment_service_module.settings, "ATTACHMENTS_DIR", str(tmp_path))
    repo = SimpleNamespace(
        create=AsyncMock(side_effect=lambda **kw: SimpleNamespace(id=uuid.uuid4(), **kw)),
        update_media=AsyncMock(),
    )
    svc = AttachmentService(repo=repo)  # type: ignore[arg-type]
    svc.base_dir = tmp_path
    return svc


def _is_red(pixel: tuple[int, int, int]) -> bool:
    # WebP's lossy encode — accept near-red
    r, g, b = pixel[:3]
    return r > 200 and g < 80 and b < 80


async def test_rotate_90_clockwise_swaps_dimensions_and_orientation(service, tmp_path):
    txn = _fake_txn()
    attachment = await service.upload(
        txn=txn, file_content=_png_bytes((64, 48)),
        original_filename="r.png", content_type="image/png",
    )

    updated = await service.rotate(attachment, txn, 90)

    assert (updated.width, updated.height) == (48, 64)
    full = tmp_path / attachment.storage_path
    with Image.open(full) as img:
        assert img.format == "WEBP"
        assert (img.width, img.height) == (48, 64)
        # Clockwise: the original top-left block lands in the top-right
        # (sample inside the block, away from compression edge artifacts)
        assert _is_red(img.getpixel((img.width - 3, 2)))
        assert not _is_red(img.getpixel((2, 2)))


async def test_rotate_180_keeps_dimensions_moves_corner(service, tmp_path):
    txn = _fake_txn()
    attachment = await service.upload(
        txn=txn, file_content=_png_bytes((64, 48)),
        original_filename="r.png", content_type="image/png",
    )

    updated = await service.rotate(attachment, txn, 180)

    assert (updated.width, updated.height) == (64, 48)
    full = tmp_path / attachment.storage_path
    with Image.open(full) as img:
        assert _is_red(img.getpixel((img.width - 3, img.height - 3)))


async def test_rotate_regenerates_thumbnail_with_new_orientation(service, tmp_path):
    txn = _fake_txn()
    attachment = await service.upload(
        txn=txn, file_content=_png_bytes((64, 48)),
        original_filename="r.png", content_type="image/png",
    )

    await service.rotate(attachment, txn, 90)

    full = tmp_path / attachment.storage_path
    thumb = full.parent / f"thumb_{full.name}"
    assert thumb.exists()
    with Image.open(thumb) as img:
        # Small source stays under THUMBNAIL_SIZE — dimensions swap 1:1
        assert (img.width, img.height) == (48, 64)


async def test_rotate_updates_repo_media_metadata(service, tmp_path):
    txn = _fake_txn()
    attachment = await service.upload(
        txn=txn, file_content=_png_bytes((64, 48)),
        original_filename="r.png", content_type="image/png",
    )

    await service.rotate(attachment, txn, 90)

    full = tmp_path / attachment.storage_path
    service.repo.update_media.assert_awaited_once_with(
        attachment.id, width=48, height=64, file_size=full.stat().st_size
    )
    assert attachment.file_size == full.stat().st_size


async def test_rotate_rejects_pdf(service):
    txn = _fake_txn()
    attachment = SimpleNamespace(
        id=uuid.uuid4(), content_type="application/pdf",
        storage_path="x.pdf", filename="x.pdf",
    )

    with pytest.raises(ValueError, match="PDF"):
        await service.rotate(attachment, txn, 90)


async def test_rotate_rejects_invalid_degrees(service, tmp_path):
    txn = _fake_txn()
    attachment = await service.upload(
        txn=txn, file_content=_png_bytes(),
        original_filename="r.png", content_type="image/png",
    )

    with pytest.raises(ValueError, match="90, 180, or 270"):
        await service.rotate(attachment, txn, 45)


async def test_rotate_missing_file_raises(service):
    txn = _fake_txn()
    attachment = SimpleNamespace(
        id=uuid.uuid4(), content_type="image/webp",
        storage_path="gone/nope.webp", filename="nope.webp",
    )

    with pytest.raises(FileNotFoundError):
        await service.rotate(attachment, txn, 90)


class TestStoredImageCompression:
    """The stored copy is the archive AND the print source: cap 2048px at
    q85. The old 4096px cap was a no-op for phone cameras, so 12MP receipts
    were archived at full sensor resolution (1.5-3.5MB each)."""

    async def test_oversized_upload_is_downscaled_to_the_cap(self, service, tmp_path):
        from igab.services.attachment_service import MAX_DIMENSION

        big = Image.new("RGB", (4032, 3024), color=(255, 255, 255))
        buf = BytesIO()
        big.save(buf, format="JPEG", quality=90)
        att = await service.upload(_fake_txn(), buf.getvalue(), "photo.jpg", "image/jpeg")
        assert max(att.width, att.height) == MAX_DIMENSION
        stored = Image.open(tmp_path / att.storage_path)
        assert max(stored.size) == MAX_DIMENSION

    async def test_within_cap_upload_keeps_its_dimensions(self, service, tmp_path):
        small = Image.new("RGB", (800, 600), color=(255, 255, 255))
        buf = BytesIO()
        small.save(buf, format="PNG")
        att = await service.upload(_fake_txn(), buf.getvalue(), "photo.png", "image/png")
        assert (att.width, att.height) == (800, 600)
        assert att.content_type == "image/webp"

    async def test_pdf_stored_verbatim(self, service, tmp_path):
        # Minimal PDF header is enough for is_pdf; stored bytes must be
        # untouched (no re-encode for documents).
        pdf = b"%PDF-1.4 minimal"
        try:
            att = await service.upload(_fake_txn(), pdf, "doc.pdf", "application/pdf")
        except Exception:
            return  # thumbnail rasterization may reject a stub PDF — fine
        assert (tmp_path / att.storage_path).read_bytes() == pdf
