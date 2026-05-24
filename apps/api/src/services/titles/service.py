from datetime import timedelta

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
    )


def _to_title(d: dict) -> Title:
    return Title(
        titleId=d["titleId"],
        title=d["title"],
        author=d["author"],
        coverUrl=_signed_url(d["coverKey"]),
        markdownUrl=_signed_url(d["parsedMdKey"]),
        toc=[TocEntry(**e) for e in (d.get("toc") or [])],
        tocSource=d.get("tocSource") or "skeleton",
        createdAt=d["createdAt"],
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


def delete_for_user(uid: str, title_id: str) -> None:
    # GCS first — if Firestore wipe fails the doc still references the blobs.
    for blob in bucket.list_blobs(prefix=f"users/{uid}/titles/{title_id}/"):
        blob.delete()
    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    firestore_client.recursive_delete(ref)
