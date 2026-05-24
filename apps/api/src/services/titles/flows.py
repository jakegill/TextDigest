import asyncio
import json
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

from google.cloud.firestore import SERVER_TIMESTAMP

from ...dependencies import bucket, firestore_client
from . import cover, mineru, toc, vector_index

logger = logging.getLogger("uvicorn.error")


@contextmanager
def timed(title_id: str, step: str) -> Iterator[None]:
    logger.info("[%s] %s...", title_id, step)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        logger.info("[%s] %s done in %.2fs", title_id, step, time.perf_counter() - t0)


def _upload(key: str, data: bytes, content_type: str) -> None:
    bucket.blob(key).upload_from_string(data, content_type=content_type)


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
        _upload(source_key, pdf_bytes, "application/pdf")

    with timed(title_id, "render cover.png"):
        cover_png = await asyncio.to_thread(cover.render_first_page_png, pdf_bytes)

    with timed(title_id, "upload cover.png → gcs"):
        _upload(cover_key, cover_png, "image/png")

    with timed(title_id, "gemini metadata extract"):
        meta = await asyncio.to_thread(cover.extract_metadata, cover_png)

    with timed(title_id, "mineru parse"):
        parse_result = await mineru.parse_pdf(title_id, pdf_bytes)
    parsed = parse_result.markdown
    content_list = parse_result.content_list

    logger.info(
        "[%s] parsed: %d chars; preview: %s...", title_id, len(parsed), parsed[:300]
    )

    with timed(title_id, "upload parsed.md → gcs"):
        _upload(parsed_md_key, parsed.encode("utf-8"), "text/markdown")

    with timed(title_id, "upload content_list.json → gcs"):
        _upload(
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
        _upload(
            toc_key,
            json.dumps([e.model_dump() for e in toc_entries]).encode("utf-8"),
            "application/json",
        )

    with timed(title_id, "firestore write"):
        await asyncio.to_thread(
            _write_title_doc,
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


def _write_title_doc(
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
    toc: list,
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
