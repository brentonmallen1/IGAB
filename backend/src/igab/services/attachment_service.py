import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from igab.config import settings
from igab.db.models import Transaction, TransactionAttachment
from igab.repositories.attachment_repo import AttachmentRepository

# iPhone cameras produce HEIC ("Keep Originals" setting); plain Pillow can't
# decode it even though the API accepts the content type.
register_heif_opener()

WEBP_QUALITY = 90
MAX_DIMENSION = 4096
THUMBNAIL_SIZE = (400, 400)


class AttachmentService:
    def __init__(self, repo: AttachmentRepository) -> None:
        self.repo = repo
        self.base_dir = Path(settings.ATTACHMENTS_DIR)

    def _build_storage_path(self, txn: Transaction, filename: str) -> Path:
        """Layout for NEW uploads only. Existing files must be located via the
        attachment's stored storage_path — the transaction date may have been
        edited since upload, so re-deriving the path from txn.date is wrong."""
        txn_date: date = txn.date
        return (
            self.base_dir
            / str(txn_date.year)
            / f"{txn_date.month:02d}"
            / f"{txn_date.day:02d}"
            / str(txn.id)
            / filename
        )

    def _resolve_path(self, attachment: TransactionAttachment, txn: Transaction) -> Path:
        if attachment.storage_path:
            return self.base_dir / attachment.storage_path
        # Legacy rows without a stored path (pre-migration)
        return self._build_storage_path(txn, attachment.filename)

    async def upload(
        self,
        txn: Transaction,
        file_content: bytes,
        original_filename: str,
        content_type: str,
    ) -> TransactionAttachment:
        from igab.utils.pdf import is_pdf

        if content_type == "application/pdf" or is_pdf(file_content):
            return await self._upload_pdf(txn, file_content, original_filename)

        file_id = uuid.uuid4()
        filename = f"{file_id}.webp"

        img = Image.open(BytesIO(file_content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

        storage_path = self._build_storage_path(txn, filename)
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        img.save(storage_path, "WEBP", quality=WEBP_QUALITY)
        file_size = storage_path.stat().st_size

        thumb = img.copy()
        thumb.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        thumb_path = storage_path.parent / f"thumb_{filename}"
        thumb.save(thumb_path, "WEBP", quality=80)

        attachment = await self.repo.create(
            transaction_id=txn.id,
            filename=filename,
            original_filename=original_filename,
            content_type="image/webp",
            file_size=file_size,
            width=img.width,
            height=img.height,
            storage_path=str(storage_path.relative_to(self.base_dir)),
        )
        return attachment

    async def _upload_pdf(
        self, txn: Transaction, file_content: bytes, original_filename: str
    ) -> TransactionAttachment:
        """PDFs are stored verbatim (no lossy re-encode of a document);
        the thumbnail is the rendered first page as WebP, following the
        thumb_{filename} convention so path resolution stays uniform."""
        from igab.utils.pdf import render_pdf_first_page

        file_id = uuid.uuid4()
        filename = f"{file_id}.pdf"

        # Render before writing anything: a corrupt PDF should fail the
        # upload, not leave a file we can never preview or extract from.
        page_png = render_pdf_first_page(file_content)
        page = Image.open(BytesIO(page_png))
        if page.mode != "RGB":
            page = page.convert("RGB")

        storage_path = self._build_storage_path(txn, filename)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(file_content)

        thumb = page.copy()
        thumb.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        thumb.save(storage_path.parent / f"thumb_{filename}", "WEBP", quality=80)

        return await self.repo.create(
            transaction_id=txn.id,
            filename=filename,
            original_filename=original_filename,
            content_type="application/pdf",
            file_size=len(file_content),
            width=page.width,
            height=page.height,
            storage_path=str(storage_path.relative_to(self.base_dir)),
        )

    def get_file_path(self, attachment: TransactionAttachment, txn: Transaction) -> Path:
        return self._resolve_path(attachment, txn)

    def get_thumbnail_path(self, attachment: TransactionAttachment, txn: Transaction) -> Path:
        base = self._resolve_path(attachment, txn)
        return base.parent / f"thumb_{base.name}"

    async def delete(self, attachment: TransactionAttachment, txn: Transaction) -> None:
        file_path = self._resolve_path(attachment, txn)
        thumb_path = file_path.parent / f"thumb_{file_path.name}"

        if file_path.exists():
            file_path.unlink()
        if thumb_path.exists():
            thumb_path.unlink()

        try:
            file_path.parent.rmdir()
        except OSError:
            pass

        await self.repo.delete_attachment(attachment.id)
