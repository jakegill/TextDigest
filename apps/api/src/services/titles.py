import logging
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

from . import mineru, storage

logger = logging.getLogger("uvicorn.error")


@contextmanager
def timed(title_id: str, step: str) -> Iterator[None]:
    logger.info("[%s] %s...", title_id, step)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        logger.info("[%s] %s done in %.2fs", title_id, step, time.perf_counter() - t0)


async def ingest(pdf_bytes: bytes, filename: str | None) -> dict[str, object]:
    title_id = str(uuid.uuid4())
    logger.info(
        "[%s] upload received: %s (%.1f KB)", title_id, filename, len(pdf_bytes) / 1024
    )
    request_start = time.perf_counter()

    with timed(title_id, "upload source.pdf → gcs"):
        storage.upload_bytes(
            f"titles/{title_id}/source.pdf", pdf_bytes, "application/pdf"
        )

    with timed(title_id, "mineru parse"):
        parsed = await mineru.parse_pdf(title_id, pdf_bytes)

    logger.info(
        "[%s] parsed: %d chars; preview: %s...", title_id, len(parsed), parsed[:300]
    )

    with timed(title_id, "upload parsed.md → gcs"):
        storage.upload_bytes(
            f"titles/{title_id}/parsed.md", parsed.encode("utf-8"), "text/markdown"
        )

    total = time.perf_counter() - request_start
    logger.info("[%s] /titles total: %.2fs", title_id, total)

    return {"titleId": title_id, "previewChars": len(parsed)}
