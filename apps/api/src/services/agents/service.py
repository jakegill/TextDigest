from datetime import datetime, timezone
from typing import Any

from google.cloud.firestore import ArrayUnion, Query, SERVER_TIMESTAMP

from ...dependencies import firestore_client

_COLLECTIONS = {
    "questions": "agent_conversations",
    "title-finder": "find_title_conversations",
}


def _collection(uid: str, agent: str):
    name = _COLLECTIONS.get(agent)
    if not name:
        raise ValueError(f"unknown agent: {agent!r}")
    return (
        firestore_client.collection("users")
        .document(uid)
        .collection(name)
    )


def _doc(uid: str, agent: str, conversation_id: str):
    return _collection(uid, agent).document(conversation_id)


def append_turn(
    uid: str,
    agent: str,
    conversation_id: str,
    user_msg: str,
    assistant_msg: str,
    *,
    doc_meta: dict[str, Any] | None = None,
    assistant_meta: dict[str, Any] | None = None,
) -> None:
    ref = _doc(uid, agent, conversation_id)
    snap = ref.get()
    now = datetime.now(timezone.utc).isoformat()
    assistant_turn: dict[str, Any] = {"role": "assistant", "content": assistant_msg, "ts": now}
    if assistant_meta:
        assistant_turn.update(assistant_meta)
    turn = [
        {"role": "user", "content": user_msg, "ts": now},
        assistant_turn,
    ]
    if snap.exists:
        ref.update({"messages": ArrayUnion(turn), "updatedAt": SERVER_TIMESTAMP})
    else:
        doc: dict[str, Any] = {
            "uid": uid,
            "agent": agent,
            "messages": turn,
            "createdAt": SERVER_TIMESTAMP,
            "updatedAt": SERVER_TIMESTAMP,
        }
        if doc_meta:
            doc.update(doc_meta)
        ref.set(doc)


def create_with_title(
    uid: str,
    agent: str,
    conversation_id: str,
    generated_title: str,
    *,
    doc_meta: dict[str, Any] | None = None,
) -> str:
    """Set the conversation's title. Idempotent: if a title already exists, returns it
    unchanged. If the doc is missing, creates it; if it exists without a title, patches in."""
    ref = _doc(uid, agent, conversation_id)
    snap = ref.get()
    if snap.exists:
        data = snap.to_dict() or {}
        existing = (data.get("title") or "").strip()
        if existing:
            return existing
        ref.update({"title": generated_title, "updatedAt": SERVER_TIMESTAMP})
        return generated_title
    doc: dict[str, Any] = {
        "uid": uid,
        "agent": agent,
        "title": generated_title,
        "messages": [],
        "createdAt": SERVER_TIMESTAMP,
        "updatedAt": SERVER_TIMESTAMP,
    }
    if doc_meta:
        doc.update(doc_meta)
    ref.set(doc)
    return generated_title


def bump(uid: str, agent: str, conversation_id: str) -> None:
    _doc(uid, agent, conversation_id).update({"updatedAt": SERVER_TIMESTAMP})


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def list_for_user(uid: str, agent: str, limit: int = 50) -> list[dict[str, Any]]:
    q = _collection(uid, agent).order_by("updatedAt", direction=Query.DESCENDING).limit(limit)
    out: list[dict[str, Any]] = []
    for snap in q.stream():
        d = snap.to_dict() or {}
        d["conversationId"] = snap.id
        d["createdAt"] = _iso(d.get("createdAt"))
        d["updatedAt"] = _iso(d.get("updatedAt"))
        out.append(d)
    return out


def get_for_user(uid: str, agent: str, conversation_id: str) -> dict[str, Any] | None:
    snap = _doc(uid, agent, conversation_id).get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    d["conversationId"] = snap.id
    d["createdAt"] = _iso(d.get("createdAt"))
    d["updatedAt"] = _iso(d.get("updatedAt"))
    return d
