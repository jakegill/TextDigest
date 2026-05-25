import asyncio
import logging

from google.cloud.firestore import SERVER_TIMESTAMP

from ...dependencies import firestore_client

logger = logging.getLogger("uvicorn.error")

DELETE_DELAY_SECONDS = 10


def _doc(uid: str, task_id: str):
    return (
        firestore_client.collection("users")
        .document(uid)
        .collection("processing")
        .document(task_id)
    )


def init(uid: str, task_id: str) -> None:
    _doc(uid, task_id).set(
        {
            "percent": 0,
            "stage": "queued",
            "titleId": None,
            "error": None,
            "updatedAt": SERVER_TIMESTAMP,
        }
    )


def update(
    uid: str,
    task_id: str,
    *,
    percent: int,
    stage: str,
    title_id: str | None = None,
    title: str | None = None,
    author: str | None = None,
    cover_url: str | None = None,
) -> None:
    patch: dict = {"percent": percent, "stage": stage, "updatedAt": SERVER_TIMESTAMP}
    if title_id is not None:
        patch["titleId"] = title_id
    if title is not None:
        patch["title"] = title
    if author is not None:
        patch["author"] = author
    if cover_url is not None:
        patch["coverUrl"] = cover_url
    _doc(uid, task_id).set(patch, merge=True)
    logger.info("[progress %s] write stage=%s percent=%d", task_id, stage, percent)


def fail(uid: str, task_id: str, error: str) -> None:
    _doc(uid, task_id).set(
        {
            "stage": "failed",
            "error": error,
            "updatedAt": SERVER_TIMESTAMP,
        },
        merge=True,
    )


def read(uid: str, task_id: str) -> dict | None:
    snap = _doc(uid, task_id).get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    updated_at = d.get("updatedAt")
    return {
        "percent": int(d.get("percent", 0)),
        "stage": d.get("stage", "queued"),
        "titleId": d.get("titleId"),
        "title": d.get("title"),
        "author": d.get("author"),
        "coverUrl": d.get("coverUrl"),
        "error": d.get("error"),
        "updatedAt": updated_at.isoformat() if updated_at else None,
    }


async def delete_after_delay(
    uid: str, task_id: str, delay: int = DELETE_DELAY_SECONDS
) -> None:
    await asyncio.sleep(delay)
    await asyncio.to_thread(_doc(uid, task_id).delete)
