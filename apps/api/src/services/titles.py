import asyncio
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

from . import cover, firestore, metadata, mineru, storage

logger = logging.getLogger("uvicorn.error")


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

    with timed(title_id, "upload source.pdf → gcs"):
        storage.upload_bytes(source_key, pdf_bytes, "application/pdf")

    with timed(title_id, "render cover.png"):
        cover_png = await asyncio.to_thread(cover.render_first_page_png, pdf_bytes)

    with timed(title_id, "upload cover.png → gcs"):
        storage.upload_bytes(cover_key, cover_png, "image/png")

    with timed(title_id, "gemini metadata extract"):
        meta = await asyncio.to_thread(metadata.extract_from_cover, cover_png)

    with timed(title_id, "mineru parse"):
        parsed = await mineru.parse_pdf(title_id, pdf_bytes)

    logger.info(
        "[%s] parsed: %d chars; preview: %s...", title_id, len(parsed), parsed[:300]
    )

    with timed(title_id, "upload parsed.md → gcs"):
        storage.upload_bytes(parsed_md_key, parsed.encode("utf-8"), "text/markdown")

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
        )

    total = time.perf_counter() - request_start
    logger.info(
        "[%s] /titles total: %.2fs (title=%r, author=%r)",
        title_id,
        total,
        meta.title,
        meta.author,
    )

    return {
        "titleId": title_id,
        "title": meta.title,
        "author": meta.author,
        "previewChars": len(parsed),
    }
