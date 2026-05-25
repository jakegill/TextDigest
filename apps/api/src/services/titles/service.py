import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from google.cloud.firestore import Query

from ...dependencies import bucket, firestore_client
from ...models.titles import Title, TitleMetadata, TocEntry


def _signed_url(key: str, ttl_seconds: int = 3600) -> str:
    return bucket.blob(key).generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=ttl_seconds),
        method="GET",
    )


def _to_metadata(d: dict) -> TitleMetadata:
    return TitleMetadata(
        titleId=d["titleId"],
        title=d["title"],
        author=d["author"],
        coverUrl=_signed_url(d["coverKey"]),
        createdAt=d["createdAt"],
        isProcessing=bool(d.get("isProcessing", False)),
        processingError=d.get("processingError"),
        lastViewed=d.get("lastViewed"),
        pageNumber=d.get("pageNumber"),
    )


def _to_title(d: dict) -> Title:
    parsed_md_key = d.get("parsedMdKey")
    return Title(
        titleId=d["titleId"],
        title=d["title"],
        author=d["author"],
        coverUrl=_signed_url(d["coverKey"]),
        markdownUrl=_signed_url(parsed_md_key) if parsed_md_key else None,
        toc=[TocEntry(**e) for e in (d.get("toc") or [])],
        tocSource=d.get("tocSource"),
        createdAt=d["createdAt"],
        isProcessing=bool(d.get("isProcessing", False)),
        processingError=d.get("processingError"),
        lastViewed=d.get("lastViewed"),
        pageNumber=d.get("pageNumber"),
    )


def list_for_user(uid: str) -> list[TitleMetadata]:
    coll = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .order_by("createdAt", direction=Query.DESCENDING)
    )
    return [
        _to_metadata({**doc.to_dict(), "titleId": doc.id}) for doc in coll.stream()
    ]


def get_for_user(uid: str, title_id: str) -> Title:
    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "title not found")
    return _to_title({**snap.to_dict(), "titleId": snap.id})


def content_list_for_user(uid: str, title_id: str) -> list[dict]:
    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "title not found")
    d = snap.to_dict() or {}
    key = d.get("contentListKey")
    if not key:
        return []
    blocks: list[dict] = json.loads(
        bucket.blob(key).download_as_bytes().decode("utf-8")
    )
    images_prefix = f"users/{uid}/titles/{title_id}/"
    for b in blocks:
        p = b.get("img_path")
        if p:
            b["img_path"] = _signed_url(images_prefix + p)
    return blocks


def update_for_user(
    uid: str,
    title_id: str,
    page_number: int | None,
    last_viewed: datetime | None,
) -> None:
    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    if not ref.get().exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "title not found")
    payload: dict = {"lastViewed": last_viewed or datetime.now(timezone.utc)}
    if page_number is not None:
        payload["pageNumber"] = page_number
    ref.update(payload)


def delete_for_user(uid: str, title_id: str) -> None:
    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    firestore_client.recursive_delete(ref)
    for blob in bucket.list_blobs(prefix=f"users/{uid}/titles/{title_id}/"):
        blob.delete()
