from fastapi import APIRouter, UploadFile

from ..services import titles as titles_service

router = APIRouter(prefix="/titles", tags=["titles"])


@router.post("")
async def upload_title(file: UploadFile) -> dict[str, object]:
    pdf_bytes = await file.read()
    return await titles_service.ingest(pdf_bytes, file.filename)
