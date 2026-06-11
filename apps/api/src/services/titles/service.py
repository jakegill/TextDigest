import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from google.cloud.firestore import Query

from ...dependencies import bucket, firestore_client, signing_credentials
from ...models.titles import Title, TitleMetadata, TocEntry
from . import vector_index

MAX_PAGE_RANGE = 50


def _signed_url(key: str, ttl_seconds: int = 3600) -> str:
    return bucket.blob(key).generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=ttl_seconds),
        method="GET",
        credentials=signing_credentials,
    )


def signed_upload_url(key: str, content_type: str, ttl_seconds: int = 600) -> str:
    return bucket.blob(key).generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=ttl_seconds),
        method="PUT",
        content_type=content_type,
        credentials=signing_credentials,
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
        pageCount=d.get("pageCount"),
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
    # Legacy stub docs (failure writes from before update() guarded them)
    # lack the core fields; skip rather than 500 the whole list.
    return [
        _to_metadata({**d, "titleId": doc.id})
        for doc in coll.stream()
        if (d := doc.to_dict() or {})
        and all(k in d for k in ("title", "coverKey", "createdAt"))
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


async def content_list_for_user(
    uid: str,
    title_id: str,
    start_page: int,
    end_page: int,
) -> list[dict]:
    if start_page < 0 or end_page < start_page:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "invalid page range",
        )
    if end_page - start_page + 1 > MAX_PAGE_RANGE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"page range exceeds max of {MAX_PAGE_RANGE}",
        )

    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    snap = await asyncio.to_thread(ref.get)
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "title not found")
    d = snap.to_dict() or {}
    pages_prefix = d.get("pagesPrefix")
    page_count = d.get("pageCount")
    if not pages_prefix or not page_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "title not finished processing",
        )

    capped_end = min(end_page, page_count - 1)
    if capped_end < start_page:
        return []

    shard_keys = [
        f"{pages_prefix}/{i:05d}.json" for i in range(start_page, capped_end + 1)
    ]
    shards = await asyncio.gather(
        *(asyncio.to_thread(bucket.blob(k).download_as_bytes) for k in shard_keys)
    )

    images_prefix = f"users/{uid}/titles/{title_id}/"
    blocks: list[dict] = []
    for raw in shards:
        for b in json.loads(raw.decode("utf-8")):
            p = b.get("img_path")
            if p:
                b["img_path"] = _signed_url(images_prefix + p)
            blocks.append(b)
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
    vector_index.delete(uid, title_id)
    ref.delete()
    # title_id == task_id, so the pending/agent-staged prefixes (which survive
    # failed runs to keep retries possible) are addressable here too.
    for prefix in (
        f"users/{uid}/titles/{title_id}/",
        f"users/{uid}/pending/{title_id}/",
        f"users/{uid}/agent-staged/{title_id}/",
    ):
        for blob in bucket.list_blobs(prefix=prefix):
            blob.delete()
