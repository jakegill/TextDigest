import asyncio
import json
import logging
import re
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..middleware.auth import get_current_uid
from ..services.agents import questions, service, title_finder
from ..services.titles import cloud_tasks, progress

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
                body.query,
                full,
                doc_meta={
                    "titleId": body.titleId,
                    "titleName": body.title,
                    "author": body.author,
                },
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
        "questions",
        conversation_id,
        title,
        doc_meta={
            "titleId": body.titleId,
            "titleName": body.titleName,
            "author": body.author,
        },
    )
    return {"title": saved}


@router.put("/questions/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_conversation(
    conversation_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> None:
    await asyncio.to_thread(service.bump, uid, "questions", conversation_id)


@router.get("/questions/conversations")
async def list_conversations(
    uid: Annotated[str, Depends(get_current_uid)],
) -> list[dict]:
    docs = await asyncio.to_thread(service.list_for_user, uid, "questions")
    return [
        {
            "conversationId": d["conversationId"],
            "title": d.get("title") or "",
            "titleId": d.get("titleId") or "",
            "titleName": d.get("titleName") or "",
            "updatedAt": d.get("updatedAt"),
        }
        for d in docs
    ]


@router.get("/questions/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict:
    doc = await asyncio.to_thread(service.get_for_user, uid, "questions", conversation_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "conversationId": doc["conversationId"],
        "title": doc.get("title") or "",
        "titleId": doc.get("titleId") or "",
        "titleName": doc.get("titleName") or "",
        "author": doc.get("author") or "",
        "messages": doc.get("messages") or [],
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


class _LibraryItem(BaseModel):
    title: str
    author: str


class _FindTitleRequest(BaseModel):
    conversationId: str
    query: str
    existingTitles: list[_LibraryItem] = []
    history: list[_Turn] = []


@router.post("/title-finder")
async def post_title_finder(
    body: _FindTitleRequest,
    uid: Annotated[str, Depends(get_current_uid)],
) -> StreamingResponse:
    existing = [t.model_dump() for t in body.existingTitles]
    history = [t.model_dump() for t in body.history]

    async def stream() -> AsyncIterator[bytes]:
        text_acc: list[str] = []
        candidates_acc: list[dict] = []
        actions_acc: list[dict] = []
        try:
            yield b'data: {"event":"start"}\n\n'
            async for ev in title_finder.stream_search(body.query, uid, existing, history):
                event = ev.get("event")
                if event in ("thinking", "research_chunk"):
                    text_acc.append(str(ev.get("body") or ""))
                elif event == "candidates":
                    body_val = ev.get("body")
                    if isinstance(body_val, list):
                        candidates_acc = body_val
                elif event == "subagent_call":
                    sub = ev.get("body") or {}
                    agent = sub.get("agent")
                    inp = sub.get("input") or {}
                    if agent == "research" and inp.get("topic"):
                        actions_acc.append({"kind": "research", "topic": inp["topic"]})
                    elif agent == "search" and inp.get("query"):
                        actions_acc.append({"kind": "search", "query": inp["query"]})
                    elif agent == "verify" and inp.get("url"):
                        actions_acc.append({"kind": "verify", "url": inp["url"]})
                elif event == "browser_action":
                    ba = ev.get("body") or {}
                    action = ba.get("action")
                    args = ba.get("args") or {}
                    if action == "navigate" and args.get("url"):
                        actions_acc.append({"kind": "browse", "url": args["url"]})
                    elif action == "search" and args.get("query"):
                        actions_acc.append({"kind": "browser_search", "query": args["query"]})
                payload = json.dumps(ev, separators=(",", ":"))
                yield f"data: {payload}\n\n".encode("utf-8")
            meta: dict[str, Any] = {}
            if candidates_acc:
                meta["candidates"] = candidates_acc
            if actions_acc:
                meta["actions"] = actions_acc
            await asyncio.to_thread(
                service.append_turn,
                uid,
                "title-finder",
                body.conversationId,
                body.query,
                _strip_sentinel("".join(text_acc)),
                assistant_meta=(meta or None),
            )
            yield b'data: {"event":"done"}\n\n'
        except Exception as e:
            logger.exception("[agents title-finder] failed")
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


_CANDIDATES_TAG_RE = re.compile(r"<candidates>[\s\S]*?</candidates>")


def _strip_sentinel(text: str) -> str:
    return _CANDIDATES_TAG_RE.sub("", text).strip()


class _CreateFindTitleConversationRequest(BaseModel):
    firstMessage: str


@router.post("/title-finder/conversations/{conversation_id}")
async def create_find_title_conversation(
    conversation_id: str,
    body: _CreateFindTitleConversationRequest,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict[str, str]:
    title = await questions.generate_title(body.firstMessage)
    saved = await asyncio.to_thread(
        service.create_with_title,
        uid,
        "title-finder",
        conversation_id,
        title,
    )
    return {"title": saved}


@router.put(
    "/title-finder/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_find_title_conversation(
    conversation_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> None:
    await asyncio.to_thread(service.bump, uid, "title-finder", conversation_id)


@router.get("/title-finder/conversations")
async def list_find_title_conversations(
    uid: Annotated[str, Depends(get_current_uid)],
) -> list[dict]:
    docs = await asyncio.to_thread(service.list_for_user, uid, "title-finder")
    return [
        {
            "conversationId": d["conversationId"],
            "title": d.get("title") or "",
            "updatedAt": d.get("updatedAt"),
        }
        for d in docs
    ]


@router.get("/title-finder/conversations/{conversation_id}")
async def get_find_title_conversation(
    conversation_id: str,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict:
    doc = await asyncio.to_thread(
        service.get_for_user, uid, "title-finder", conversation_id,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "conversationId": doc["conversationId"],
        "title": doc.get("title") or "",
        "messages": doc.get("messages") or [],
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


class _IngestRequest(BaseModel):
    taskId: str
    sourceKey: str
    filename: str | None = None


@router.post("/title-finder/ingest", status_code=status.HTTP_202_ACCEPTED)
async def post_title_finder_ingest(
    body: _IngestRequest,
    request: Request,
    uid: Annotated[str, Depends(get_current_uid)],
) -> dict[str, str]:
    expected_prefix = f"users/{uid}/agent-staged/"
    if not body.sourceKey.startswith(expected_prefix):
        raise HTTPException(status_code=403, detail="source_key uid mismatch")
    await asyncio.to_thread(progress.init, uid, body.taskId)
    api_base_url = str(request.base_url).rstrip("/")
    await cloud_tasks.enqueue_process(
        api_base_url, uid, body.taskId, body.sourceKey, body.filename,
    )
    logger.info(
        "[agents title-finder ingest] uid=%s taskId=%s enqueued", uid, body.taskId,
    )
    return {"taskId": body.taskId}
