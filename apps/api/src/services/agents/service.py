from datetime import datetime, timezone
from typing import Any

from google.cloud.firestore import ArrayUnion, Query, SERVER_TIMESTAMP

from ...dependencies import firestore_client


def _collection(uid: str):
    return (
        firestore_client.collection("users")
        .document(uid)
        .collection("agent_conversations")
    )


def _doc(uid: str, conversation_id: str):
    return _collection(uid).document(conversation_id)


def append_turn(
    uid: str,
    agent: str,
    conversation_id: str,
    title_id: str,
    title: str,
    author: str,
    user_msg: str,
    assistant_msg: str,
) -> None:
    ref = _doc(uid, conversation_id)
    snap = ref.get()
    now = datetime.now(timezone.utc).isoformat()
    turn = [
        {"role": "user", "content": user_msg, "ts": now},
        {"role": "assistant", "content": assistant_msg, "ts": now},
    ]
    if snap.exists:
        ref.update({"messages": ArrayUnion(turn), "updatedAt": SERVER_TIMESTAMP})
    else:
        ref.set(
            {
                "uid": uid,
                "agent": agent,
                "titleId": title_id,
                "titleName": title,
                "author": author,
                "messages": turn,
                "createdAt": SERVER_TIMESTAMP,
                "updatedAt": SERVER_TIMESTAMP,
            }
        )


def create_with_title(
    uid: str,
    conversation_id: str,
    generated_title: str,
    title_id: str,
    title_name: str,
    author: str,
) -> str:
    """Set the conversation's title. Idempotent: if a title already exists, returns it
    unchanged. If the doc is missing, creates it; if it exists without a title, patches in."""
    ref = _doc(uid, conversation_id)
    snap = ref.get()
    if snap.exists:
        data = snap.to_dict() or {}
        existing = (data.get("title") or "").strip()
        if existing:
            return existing
        ref.update({"title": generated_title, "updatedAt": SERVER_TIMESTAMP})
        return generated_title
    ref.set(
        {
            "uid": uid,
            "agent": "questions",
            "title": generated_title,
            "titleId": title_id,
            "titleName": title_name,
            "author": author,
            "messages": [],
            "createdAt": SERVER_TIMESTAMP,
            "updatedAt": SERVER_TIMESTAMP,
        }
    )
    return generated_title


def bump(uid: str, conversation_id: str) -> None:
    _doc(uid, conversation_id).update({"updatedAt": SERVER_TIMESTAMP})


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def list_for_user(uid: str, limit: int = 50) -> list[dict[str, Any]]:
    q = _collection(uid).order_by("updatedAt", direction=Query.DESCENDING).limit(limit)
    out: list[dict[str, Any]] = []
    for snap in q.stream():
        d = snap.to_dict() or {}
        out.append(
            {
                "conversationId": snap.id,
                "title": d.get("title") or "",
                "titleId": d.get("titleId") or "",
                "titleName": d.get("titleName") or "",
                "updatedAt": _iso(d.get("updatedAt")),
            }
        )
    return out


def get_for_user(uid: str, conversation_id: str) -> dict[str, Any] | None:
    snap = _doc(uid, conversation_id).get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    return {
        "conversationId": snap.id,
        "title": d.get("title") or "",
        "titleId": d.get("titleId") or "",
        "titleName": d.get("titleName") or "",
        "author": d.get("author") or "",
        "messages": d.get("messages") or [],
        "createdAt": _iso(d.get("createdAt")),
        "updatedAt": _iso(d.get("updatedAt")),
    }
