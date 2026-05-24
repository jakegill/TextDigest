import asyncio
import json
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException, status

from ..models.titles import Title, TitleMetadata, TocEntry
from . import cover, firestore, metadata, mineru, storage, toc, vector_index

logger = logging.getLogger("uvicorn.error")


def list_for_user(uid: str) -> list[TitleMetadata]:
    return [_to_metadata(d) for d in firestore.list_titles(uid)]


def get_for_user(uid: str, title_id: str) -> Title:
    d = firestore.get_title(uid, title_id)
    if d is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="title not found")
    return _to_title(d)


def delete_for_user(uid: str, title_id: str) -> None:
    # GCS first — if Firestore wipe fails the doc still references the blobs.
    storage.delete_prefix(f"users/{uid}/titles/{title_id}/")
    firestore.delete_title(uid, title_id)


def _to_metadata(d: dict) -> TitleMetadata:
    return TitleMetadata(
        titleId=d["titleId"],
        title=d["title"],
        author=d["author"],
        coverUrl=storage.signed_url(d["coverKey"]),
        createdAt=d["createdAt"],
    )


def _to_title(d: dict) -> Title:
    return Title(
        titleId=d["titleId"],
        title=d["title"],
        author=d["author"],
        coverUrl=storage.signed_url(d["coverKey"]),
        markdownUrl=storage.signed_url(d["parsedMdKey"]),
        toc=[TocEntry(**e) for e in (d.get("toc") or [])],
        tocSource=d.get("tocSource") or "skeleton",
        createdAt=d["createdAt"],
    )


@contextmanager
def timed(title_id: str, step: str) -> Iterator[None]:
    logger.info("[%s] %s...", title_id, step)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        logger.info("[%s] %s done in %.2fs", title_id, step, time.perf_counter() - t0)


async def ingest(uid: str, pdf_bytes: bytes, filename: str | None) -> dict[str, object]:
    title_id = str(uuid.uuid4())
    logger.info(
        "[%s] uid=%s upload received: %s (%.1f KB)",
        title_id,
        uid,
        filename,
        len(pdf_bytes) / 1024,
    )
    request_start = time.perf_counter()

    source_key = f"users/{uid}/titles/{title_id}/source.pdf"
    parsed_md_key = f"users/{uid}/titles/{title_id}/parsed.md"
    cover_key = f"users/{uid}/titles/{title_id}/cover.png"
    content_list_key = f"users/{uid}/titles/{title_id}/content_list.json"
    toc_key = f"users/{uid}/titles/{title_id}/toc.json"

    with timed(title_id, "upload source.pdf → gcs"):
        storage.upload_bytes(source_key, pdf_bytes, "application/pdf")

    with timed(title_id, "render cover.png"):
        cover_png = await asyncio.to_thread(cover.render_first_page_png, pdf_bytes)

    with timed(title_id, "upload cover.png → gcs"):
        storage.upload_bytes(cover_key, cover_png, "image/png")

    with timed(title_id, "gemini metadata extract"):
        meta = await asyncio.to_thread(metadata.extract_from_cover, cover_png)

    with timed(title_id, "mineru parse"):
        parse_result = await mineru.parse_pdf(title_id, pdf_bytes)
    parsed = parse_result.markdown
    content_list = parse_result.content_list

    logger.info(
        "[%s] parsed: %d chars; preview: %s...", title_id, len(parsed), parsed[:300]
    )

    with timed(title_id, "upload parsed.md → gcs"):
        storage.upload_bytes(parsed_md_key, parsed.encode("utf-8"), "text/markdown")

    with timed(title_id, "upload content_list.json → gcs"):
        storage.upload_bytes(
            content_list_key,
            json.dumps(content_list).encode("utf-8"),
            "application/json",
        )

    with timed(title_id, "vectorize"):
        n_chunks = await vector_index.build(uid, title_id, content_list)
    logger.info("[%s] vector index: %d chunks", title_id, n_chunks)

    with timed(title_id, "toc extract"):
        toc_entries, toc_source = await asyncio.to_thread(
            toc.extract_toc, uid, title_id, content_list
        )
    logger.info(
        "[%s] toc: %d entries (source=%s)", title_id, len(toc_entries), toc_source
    )

    with timed(title_id, "upload toc.json → gcs"):
        storage.upload_bytes(
            toc_key,
            json.dumps([e.model_dump() for e in toc_entries]).encode("utf-8"),
            "application/json",
        )

    with timed(title_id, "firestore write"):
        await asyncio.to_thread(
            firestore.write_title,
            uid,
            title_id,
            title=meta.title,
            author=meta.author,
            source_key=source_key,
            parsed_md_key=parsed_md_key,
            cover_key=cover_key,
            content_list_key=content_list_key,
            toc_key=toc_key,
            toc=toc_entries,
            toc_source=toc_source,
        )

    total = time.perf_counter() - request_start
    logger.info(
        "[%s] /titles total: %.2fs (title=%r, author=%r, toc=%d, chunks=%d)",
        title_id,
        total,
        meta.title,
        meta.author,
        len(toc_entries),
        n_chunks,
    )

    return {
        "titleId": title_id,
        "title": meta.title,
        "author": meta.author,
        "previewChars": len(parsed),
        "tocEntries": len(toc_entries),
        "tocSource": toc_source,
        "chunkCount": n_chunks,
    }
