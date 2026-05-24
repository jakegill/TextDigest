import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, status

from ..middleware.auth import get_current_uid
from ..models.titles import Title, TitleMetadata
from ..services import titles as titles_service

router = APIRouter(prefix="/titles", tags=["titles"])


@router.get("")
async def list_titles(
    uid: Annotated[str, Depends(get_current_uid)],
) -> list[TitleMetadata]:
    return await asyncio.to_thread(titles_service.list_for_user, uid)


@router.get("/{title_id}")
async def get_title(
    title_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> Title:
    return await asyncio.to_thread(titles_service.get_for_user, uid, title_id)


@router.delete("/{title_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_title(
    title_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> None:
    await asyncio.to_thread(titles_service.delete_for_user, uid, title_id)


@router.post("")
async def upload_title(
    file: UploadFile,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict[str, object]:
    pdf_bytes = await file.read()
    return await titles_service.ingest(uid, pdf_bytes, file.filename)
