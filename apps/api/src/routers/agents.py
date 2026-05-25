import asyncio
import json
import logging
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..middleware.auth import get_current_uid
from ..services.agents import questions, service

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/agents", tags=["agents"])


class _Turn(BaseModel):
    role: str
    content: str


class _QuestionRequest(BaseModel):
    conversationId: str
    titleId: str
    title: str
    author: str
    query: str
    highlightedText: str
    pageContent: str
    history: list[_Turn]


@router.post("/questions")
async def post_question(
    body: _QuestionRequest,
    uid: Annotated[str, Depends(get_current_uid)],
) -> StreamingResponse:
    async def stream() -> AsyncIterator[bytes]:
        chunks: list[str] = []
        try:
            yield b'data: {"event":"turn-start"}\n\n'
            async for delta in questions.stream_answer(
                query=body.query,
                highlighted_text=body.highlightedText,
                page_content=body.pageContent,
                title=body.title,
                author=body.author,
                history=[t.model_dump() for t in body.history],
            ):
                chunks.append(delta)
                payload = json.dumps({"event": "chunk", "body": delta}, separators=(",", ":"))
                yield f"data: {payload}\n\n".encode("utf-8")
            full = "".join(chunks)
            await asyncio.to_thread(
                service.append_turn,
                uid,
                "questions",
                body.conversationId,
                body.titleId,
                body.title,
                body.author,
                body.query,
                full,
            )
            yield b'data: {"event":"turn-over"}\n\n'
        except Exception as e:
            logger.exception("[agents questions] failed")
            payload = json.dumps({"event": "error", "body": str(e)}, separators=(",", ":"))
            yield f"data: {payload}\n\n".encode("utf-8")

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class _CreateConversationRequest(BaseModel):
    firstMessage: str
    titleId: str
    titleName: str
    author: str


@router.post("/questions/conversations/{conversation_id}")
async def create_conversation(
    conversation_id: str,
    body: _CreateConversationRequest,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict[str, str]:
    title = await questions.generate_title(body.firstMessage)
    saved = await asyncio.to_thread(
        service.create_with_title,
        uid,
        conversation_id,
        title,
        body.titleId,
        body.titleName,
        body.author,
    )
    return {"title": saved}


@router.put("/questions/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_conversation(
    conversation_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> None:
    await asyncio.to_thread(service.bump, uid, conversation_id)


@router.get("/questions/conversations")
async def list_conversations(
    uid: Annotated[str, Depends(get_current_uid)],
) -> list[dict]:
    return await asyncio.to_thread(service.list_for_user, uid)


@router.get("/questions/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict:
    doc = await asyncio.to_thread(service.get_for_user, uid, conversation_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return doc
