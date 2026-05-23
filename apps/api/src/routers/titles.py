from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile

from ..dependencies import get_current_uid
from ..services import titles as titles_service

router = APIRouter(prefix="/titles", tags=["titles"])


@router.post("")
async def upload_title(
    file: UploadFile,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict[str, object]:
    pdf_bytes = await file.read()
    return await titles_service.ingest(uid, pdf_bytes, file.filename)
