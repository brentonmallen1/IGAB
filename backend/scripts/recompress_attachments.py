"""One-off recompression of stored attachment images to the current limits.

Attachments used to be stored as WebP quality-90 with a 4096px cap — a no-op
for phone cameras, so 12MP receipts sat on disk at 1.5-3.5MB each. New uploads
are 2048px / q85 / method=6; this walks the existing library and re-encodes
anything bigger than the current caps, updating width/height/file_size and
regenerating the thumbnail. PDFs and files already within limits are skipped.

Each re-encode is one extra lossy generation on an already-lossy WebP — at
q85 on receipt/document content that is visually irrelevant, and it is the
point of the exercise.

Run it against the same DB/volume the app uses (inside the api container):

    docker compose exec api python scripts/recompress_attachments.py [--dry-run]

or locally with the dev DB:

    cd backend && DATABASE_URL=... uv run python scripts/recompress_attachments.py
"""

import argparse
import asyncio
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

from igab.config import get_settings  # noqa: E402
from igab.db.models import TransactionAttachment  # noqa: E402
from igab.db.session import AsyncSessionLocal  # noqa: E402
from igab.services.attachment_service import (  # noqa: E402
    MAX_DIMENSION,
    THUMBNAIL_SIZE,
    WEBP_METHOD,
    WEBP_QUALITY,
)


async def main(dry_run: bool) -> None:
    base_dir = Path(get_settings().ATTACHMENTS_DIR)
    before_total = 0
    after_total = 0
    touched = 0
    skipped = 0
    missing = 0

    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(TransactionAttachment).where(
                        TransactionAttachment.content_type == "image/webp"
                    )
                )
            )
            .scalars()
            .all()
        )

        for att in rows:
            path = base_dir / att.storage_path
            if not path.exists():
                missing += 1
                continue
            size = path.stat().st_size
            img = Image.open(path)
            oversized = img.width > MAX_DIMENSION or img.height > MAX_DIMENSION
            # Under the dimension cap AND already reasonably small: leave it —
            # re-encoding those trades quality for nothing.
            if not oversized and size <= 600 * 1024:
                skipped += 1
                continue

            if img.mode not in ("RGB",):
                img = img.convert("RGB")
            if oversized:
                img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

            buf = BytesIO()
            img.save(buf, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
            new_bytes = buf.getvalue()
            if len(new_bytes) >= size:
                skipped += 1  # already smaller than we can do — keep original
                continue

            before_total += size
            after_total += len(new_bytes)
            touched += 1
            print(
                f"{att.storage_path}: {size / 1024:.0f}KB -> {len(new_bytes) / 1024:.0f}KB"
                f"{' (dry run)' if dry_run else ''}"
            )
            if dry_run:
                continue

            path.write_bytes(new_bytes)
            thumb = img.copy()
            thumb.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            thumb.save(path.parent / f"thumb_{path.name}", "WEBP", quality=80)
            att.file_size = len(new_bytes)
            att.width = img.width
            att.height = img.height

        if not dry_run:
            await session.commit()

    saved = before_total - after_total
    print(
        f"\n{touched} re-encoded, {skipped} left as-is, {missing} missing on disk. "
        f"{before_total / 1024 / 1024:.1f}MB -> {after_total / 1024 / 1024:.1f}MB "
        f"(saved {saved / 1024 / 1024:.1f}MB)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
