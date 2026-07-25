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

    def _get_storage_path(self, txn: Transaction, filename: str) -> Path:
        txn_date: date = txn.date
        return (
            self.base_dir
            / str(txn_date.year)
            / f"{txn_date.month:02d}"
            / f"{txn_date.day:02d}"
            / str(txn.id)
            / filename
        )

    def _get_thumbnail_path(self, attachment: TransactionAttachment, txn: Transaction) -> Path:
        base = self._get_storage_path(txn, attachment.filename)
        return base.parent / f"thumb_{base.name}"

    async def upload(
        self,
        txn: Transaction,
        file_content: bytes,
        original_filename: str,
        content_type: str,
    ) -> TransactionAttachment:
        file_id = uuid.uuid4()
        filename = f"{file_id}.webp"

        img = Image.open(BytesIO(file_content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

        storage_path = self._get_storage_path(txn, filename)
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
        )
        return attachment

    def get_file_path(self, attachment: TransactionAttachment, txn: Transaction) -> Path:
        return self._get_storage_path(txn, attachment.filename)

    def get_thumbnail_path(self, attachment: TransactionAttachment, txn: Transaction) -> Path:
        return self._get_thumbnail_path(attachment, txn)

    async def delete(self, attachment: TransactionAttachment, txn: Transaction) -> None:
        file_path = self._get_storage_path(txn, attachment.filename)
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
