from google.cloud.firestore import SERVER_TIMESTAMP, Query

from ..dependencies import firestore_client
from .toc import TocEntry


def write_title(
    uid: str,
    title_id: str,
    *,
    title: str,
    author: str,
    source_key: str,
    parsed_md_key: str,
    cover_key: str,
    content_list_key: str,
    toc_key: str,
    toc: list[TocEntry],
    toc_source: str,
) -> None:
    firestore_client.collection("users").document(uid).collection("titles").document(
        title_id
    ).set(
        {
            "title": title,
            "author": author,
            "sourceKey": source_key,
            "parsedMdKey": parsed_md_key,
            "coverKey": cover_key,
            "contentListKey": content_list_key,
            "tocKey": toc_key,
            "toc": [e.model_dump() for e in toc],
            "tocSource": toc_source,
            "createdAt": SERVER_TIMESTAMP,
        }
    )


def list_titles(uid: str) -> list[dict]:
    coll = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .order_by("createdAt", direction=Query.DESCENDING)
    )
    return [{**doc.to_dict(), "titleId": doc.id} for doc in coll.stream()]


def get_title(uid: str, title_id: str) -> dict | None:
    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    snap = ref.get()
    return {**snap.to_dict(), "titleId": snap.id} if snap.exists else None


def delete_title(uid: str, title_id: str) -> None:
    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    firestore_client.recursive_delete(ref)
