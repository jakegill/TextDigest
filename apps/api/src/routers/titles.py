import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..middleware.auth import get_current_uid, verify_cloud_task_oidc
from ..models.titles import Title, TitleMetadata
from ..services.titles import cloud_tasks, flows, progress, service

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/titles", tags=["titles"])

SSE_POLL_INTERVAL_S = 0.5
SSE_MAX_DURATION_S = 60 * 30  # 30 min cap — pipeline finishes well within this


class _ProcessRequest(BaseModel):
    uid: str
    taskId: str
    sourceKey: str
    filename: str | None = None


class _UploadUrlRequest(BaseModel):
    filename: str | None = None
    contentType: str = "application/pdf"


class _UploadUrlResponse(BaseModel):
    taskId: str
    sourceKey: str
    uploadUrl: str


class _StartProcessingRequest(BaseModel):
    taskId: str
    sourceKey: str
    filename: str | None = None


class _UpdateRequest(BaseModel):
    pageNumber: int | None = None
    lastViewed: datetime | None = None


@router.get("")
async def list_titles(
    uid: Annotated[str, Depends(get_current_uid)],
) -> list[TitleMetadata]:
    return await asyncio.to_thread(service.list_for_user, uid)


@router.get("/{title_id}")
async def get_title(
    title_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> Title:
    return await asyncio.to_thread(service.get_for_user, uid, title_id)


@router.get("/{title_id}/content_list")
async def get_content_list(
    title_id: str,
    startPage: int,
    endPage: int,
    uid: Annotated[str, Depends(get_current_uid)],
) -> list[dict]:
    return await service.content_list_for_user(uid, title_id, startPage, endPage)


@router.delete("/{title_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_title(
    title_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> None:
    await asyncio.to_thread(service.delete_for_user, uid, title_id)


@router.put("/{title_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_title(
    title_id: str,
    body: _UpdateRequest,
    uid: Annotated[str, Depends(get_current_uid)],
) -> None:
    await asyncio.to_thread(
        service.update_for_user, uid, title_id, body.pageNumber, body.lastViewed
    )


@router.post("/upload-url")
async def create_upload_url(
    body: _UploadUrlRequest,
    uid: Annotated[str, Depends(get_current_uid)],
) -> _UploadUrlResponse:
    task_id = str(uuid.uuid4())
    source_key = f"users/{uid}/pending/{task_id}/source.pdf"
    upload_url = await asyncio.to_thread(
        service.signed_upload_url, source_key, body.contentType
    )
    return _UploadUrlResponse(
        taskId=task_id, sourceKey=source_key, uploadUrl=upload_url
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_title(
    request: Request,
    body: _StartProcessingRequest,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict[str, str]:
    expected_key = f"users/{uid}/pending/{body.taskId}/source.pdf"
    if body.sourceKey != expected_key:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "sourceKey does not match uid/taskId"
        )
    await asyncio.to_thread(progress.init, uid, body.taskId)
    api_base_url = str(request.base_url).rstrip("/")
    await cloud_tasks.enqueue_process(
        api_base_url, uid, body.taskId, body.sourceKey, body.filename
    )
    return {"taskId": body.taskId}


@router.get("/processing/{task_id}/events")
async def processing_events(
    task_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> StreamingResponse:
    logger.info("[sse %s] open uid=%s", task_id, uid)

    async def stream() -> AsyncIterator[bytes]:
        last_payload: str | None = None
        elapsed = 0.0
        emits = 0
        try:
            while elapsed < SSE_MAX_DURATION_S:
                doc = await asyncio.to_thread(progress.read, uid, task_id)
                if doc:
                    payload = json.dumps(doc, separators=(",", ":"))
                    if payload != last_payload:
                        emits += 1
                        logger.info(
                            "[sse %s] emit #%d stage=%s",
                            task_id,
                            emits,
                            doc.get("stage"),
                        )
                        yield f"data: {payload}\n\n".encode("utf-8")
                        last_payload = payload
                    if doc["stage"] in ("done", "failed"):
                        logger.info(
                            "[sse %s] terminal stage=%s, closing stream",
                            task_id,
                            doc["stage"],
                        )
                        return
                await asyncio.sleep(SSE_POLL_INTERVAL_S)
                elapsed += SSE_POLL_INTERVAL_S
            logger.warning(
                "[sse %s] max duration reached (%ds), closing stream",
                task_id,
                SSE_MAX_DURATION_S,
            )
        finally:
            logger.info("[sse %s] closed after %d emits", task_id, emits)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/process", include_in_schema=False)
async def process(
    request: Request,
    body: _ProcessRequest,
    _: Annotated[None, Depends(verify_cloud_task_oidc)],
) -> dict[str, str]:
    """Worker endpoint. Authed via Cloud Tasks OIDC token (not Firebase)."""
    # X-CloudTasks-TaskRetryCount counts prior attempts; the queue allows 3
    # total (infra/queue.ts maxAttempts). Absent header (dev in-process mode)
    # means no retries are coming, so failures must mark the title failed now.
    retry_count = request.headers.get("X-CloudTasks-TaskRetryCount")
    is_final_attempt = retry_count is None or int(retry_count) + 1 >= 3
    await flows.stage_process(
        body.uid,
        body.taskId,
        body.sourceKey,
        body.filename,
        is_final_attempt=is_final_attempt,
    )
    return {"ok": "true"}
