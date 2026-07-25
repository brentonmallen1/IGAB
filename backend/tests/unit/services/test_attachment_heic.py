"""HEIC uploads must decode and convert like any other image.

The API's ALLOWED_CONTENT_TYPES admits image/heic (iPhone "Keep Originals"),
so the service must actually be able to open it — plain Pillow cannot without
pillow-heif's opener registered at import time.
"""

import uuid
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from igab.services import attachment_service as attachment_service_module
from igab.services.attachment_service import AttachmentService


def _heic_bytes(size: tuple[int, int] = (64, 48)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color=(120, 40, 200)).save(buf, format="HEIF")
    return buf.getvalue()


def _fake_txn() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), date=date(2026, 7, 22))


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(attachment_service_module.settings, "ATTACHMENTS_DIR", str(tmp_path))
    repo = SimpleNamespace(create=AsyncMock(side_effect=lambda **kw: SimpleNamespace(**kw)))
    svc = AttachmentService(repo=repo)  # type: ignore[arg-type]
    svc.base_dir = tmp_path
    return svc


async def test_heic_upload_converts_to_webp_with_thumbnail(service, tmp_path):
    txn = _fake_txn()

    attachment = await service.upload(
        txn=txn,
        file_content=_heic_bytes(),
        original_filename="receipt.heic",
        content_type="image/heic",
    )

    assert attachment.content_type == "image/webp"
    assert attachment.width == 64
    assert attachment.height == 48

    stored = list(tmp_path.rglob("*.webp"))
    names = sorted(p.name for p in stored)
    assert len(stored) == 2, f"expected image + thumbnail, got {names}"
    assert any(n.startswith("thumb_") for n in names)

    full = next(p for p in stored if not p.name.startswith("thumb_"))
    with Image.open(full) as img:
        assert img.format == "WEBP"
        assert (img.width, img.height) == (64, 48)


async def test_heic_with_alpha_flattens_to_rgb(service, tmp_path):
    buf = BytesIO()
    Image.new("RGBA", (32, 32), color=(10, 20, 30, 128)).save(buf, format="HEIF")
    txn = _fake_txn()

    attachment = await service.upload(
        txn=txn,
        file_content=buf.getvalue(),
        original_filename="alpha.heif",
        content_type="image/heif",
    )

    assert attachment.content_type == "image/webp"
    full = next(p for p in tmp_path.rglob("*.webp") if not p.name.startswith("thumb_"))
    with Image.open(full) as img:
        assert img.mode == "RGB"
