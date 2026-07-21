import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from igab.api.v1.schemas.attachment import AttachmentResponse
from igab.dependencies import (
    AttachmentAccess,
    CurrentUser,
    TransactionAccess,
    get_attachment_repo,
    get_attachment_service,
    get_transaction_repo,
)
from igab.repositories.attachment_repo import AttachmentRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.attachment_service import AttachmentService

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/gif",
}
MAX_FILE_SIZE = 20 * 1024 * 1024


@router.get("/transactions/{transaction_id}/attachments", response_model=list[AttachmentResponse])
async def list_attachments(
    transaction_id: TransactionAccess,
    current_user: CurrentUser,
    attachment_repo: Annotated[AttachmentRepository, Depends(get_attachment_repo)],
) -> list[AttachmentResponse]:
    attachments = await attachment_repo.get_for_transaction(transaction_id)
    return [AttachmentResponse.model_validate(a, from_attributes=True) for a in attachments]


@router.post(
    "/transactions/{transaction_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    transaction_id: TransactionAccess,
    current_user: CurrentUser,
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    attachment_service: Annotated[AttachmentService, Depends(get_attachment_service)],
    file: UploadFile = File(...),
) -> AttachmentResponse:
    txn = await txn_repo.get(transaction_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file.content_type} not allowed",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large (max 20MB)",
        )

    attachment = await attachment_service.upload(
        txn=txn,
        file_content=content,
        original_filename=file.filename or "attachment",
        content_type=file.content_type or "image/jpeg",
    )
    return AttachmentResponse.model_validate(attachment, from_attributes=True)


@router.get("/attachments/{attachment_id}")
async def get_attachment(
    attachment_id: AttachmentAccess,
    current_user: CurrentUser,
    attachment_repo: Annotated[AttachmentRepository, Depends(get_attachment_repo)],
    attachment_service: Annotated[AttachmentService, Depends(get_attachment_service)],
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
    thumbnail: bool = False,
) -> FileResponse:
    attachment = await attachment_repo.get_by_id(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    txn = await txn_repo.get(attachment.transaction_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if thumbnail:
        file_path = attachment_service.get_thumbnail_path(attachment, txn)
    else:
        file_path = attachment_service.get_file_path(attachment, txn)

    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")

    return FileResponse(
        path=file_path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: AttachmentAccess,
    current_user: CurrentUser,
    attachment_repo: Annotated[AttachmentRepository, Depends(get_attachment_repo)],
    attachment_service: Annotated[AttachmentService, Depends(get_attachment_service)],
    txn_repo: Annotated[TransactionRepository, Depends(get_transaction_repo)],
) -> None:
    attachment = await attachment_repo.get_by_id(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    txn = await txn_repo.get(attachment.transaction_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    await attachment_service.delete(attachment, txn)


@router.post("/transactions/attachments/check", response_model=dict[str, bool])
async def check_attachments(
    transaction_ids: list[uuid.UUID],
    current_user: CurrentUser,
    attachment_repo: Annotated[AttachmentRepository, Depends(get_attachment_repo)],
) -> dict[str, bool]:
    has_attachments = await attachment_repo.has_attachments(transaction_ids)
    return {str(tid): tid in has_attachments for tid in transaction_ids}
