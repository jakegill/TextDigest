import asyncio
import json
import logging
import mimetypes
import time
import uuid
from contextlib import contextmanager
from typing import Iterator

from google.cloud.firestore import SERVER_TIMESTAMP

from ...dependencies import bucket, firestore_client
from . import cover, mineru, progress, service, toc, vector_index

logger = logging.getLogger("uvicorn.error")

# Pipeline percent budgets: keep monotonic across stages.
PCT_QUEUED = 0
PCT_COVER = 3
PCT_METADATA = 8
PCT_PARSING_START = 10
PCT_PARSING_END = 75
PCT_VECTORIZING_END = 90
PCT_TOC_END = 98
PCT_DONE = 100


@contextmanager
def timed(task_id: str, step: str) -> Iterator[None]:
    logger.info("[%s] %s...", task_id, step)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        logger.info("[%s] %s done in %.2fs", task_id, step, time.perf_counter() - t0)


def _upload(key: str, data: bytes, content_type: str) -> None:
    bucket.blob(key).upload_from_string(data, content_type=content_type)


async def stage_upload(
    uid: str, pdf_bytes: bytes, filename: str | None
) -> tuple[str, str]:
    """POST /titles handler calls this. Fast: GCS upload of source.pdf to a
    pending area + init the progress doc. Returns (task_id, source_key)."""
    task_id = str(uuid.uuid4())
    source_key = f"users/{uid}/pending/{task_id}/source.pdf"

    logger.info(
        "[%s] uid=%s upload received: %s (%.1f KB)",
        task_id,
        uid,
        filename,
        len(pdf_bytes) / 1024,
    )
    with timed(task_id, "upload source.pdf → gcs (pending)"):
        await asyncio.to_thread(_upload, source_key, pdf_bytes, "application/pdf")

    await asyncio.to_thread(progress.init, uid, task_id)
    return task_id, source_key


async def stage_agent_capture(
    uid: str, pdf_bytes: bytes, filename: str | None
) -> tuple[str, str]:
    """Stages PDF bytes captured by the verify subagent to a separate prefix.
    No progress.init — so unclicked candidates don't show as pending in the
    library UI. Returns (task_id, source_key)."""
    task_id = str(uuid.uuid4())
    source_key = f"users/{uid}/agent-staged/{task_id}/source.pdf"
    logger.info(
        "[%s] uid=%s agent capture stage: %s (%.1f KB)",
        task_id, uid, filename, len(pdf_bytes) / 1024,
    )
    with timed(task_id, "upload agent-staged source.pdf → gcs"):
        await asyncio.to_thread(_upload, source_key, pdf_bytes, "application/pdf")
    return task_id, source_key


async def stage_process(
    uid: str, task_id: str, source_key: str, filename: str | None
) -> None:
    """Worker entrypoint. Drives the full pipeline with progressive Firestore
    progress writes. Writes the title doc after cover metadata is extracted
    (isProcessing=true), flips it to isProcessing=false on completion."""
    title_id = str(uuid.uuid4())
    start = time.perf_counter()
    logger.info("[%s] stage_process start (filename=%r)", task_id, filename)

    try:
        await asyncio.to_thread(
            progress.update,
            uid,
            task_id,
            percent=PCT_QUEUED,
            stage="cover",
        )

        # Re-fetch the source PDF from the pending GCS area.
        with timed(task_id, "download pending source.pdf"):
            pdf_bytes = await asyncio.to_thread(
                bucket.blob(source_key).download_as_bytes
            )

        with timed(task_id, "render cover.png"):
            cover_png = await asyncio.to_thread(cover.render_first_page_png, pdf_bytes)
        await asyncio.to_thread(
            progress.update, uid, task_id, percent=PCT_COVER, stage="metadata"
        )

        # Final canonical GCS keys keyed by titleId (move out of pending).
        final_source_key = f"users/{uid}/titles/{title_id}/source.pdf"
        cover_key = f"users/{uid}/titles/{title_id}/cover.png"
        parsed_md_key = f"users/{uid}/titles/{title_id}/parsed.md"
        content_list_key = f"users/{uid}/titles/{title_id}/content_list.json"
        toc_key = f"users/{uid}/titles/{title_id}/toc.json"
        images_prefix = f"users/{uid}/titles/{title_id}/images"

        with timed(task_id, "upload cover.png + canonical source.pdf"):
            await asyncio.to_thread(_upload, cover_key, cover_png, "image/png")
            await asyncio.to_thread(
                _upload, final_source_key, pdf_bytes, "application/pdf"
            )

        with timed(task_id, "gemini metadata extract"):
            meta = await asyncio.to_thread(cover.extract_metadata, cover_png)

        # First Firestore write of the title doc — happens after cover metadata
        # so title/author are real values. isProcessing=true until done.
        with timed(task_id, "firestore write (initial, isProcessing=true)"):
            await asyncio.to_thread(
                _write_title_doc,
                uid,
                title_id,
                fields={
                    "title": meta.title,
                    "author": meta.author,
                    "sourceKey": final_source_key,
                    "coverKey": cover_key,
                    "isProcessing": True,
                    "processingError": None,
                    "createdAt": SERVER_TIMESTAMP,
                },
                merge=False,
            )
        # Sign cover URL once, fold it into the progress doc so the SSE event
        # carries enough for the frontend to render a card immediately.
        cover_url = service._signed_url(cover_key)
        await asyncio.to_thread(
            progress.update,
            uid,
            task_id,
            percent=PCT_PARSING_START,
            stage="parsing",
            title_id=title_id,
            title=meta.title,
            author=meta.author,
            cover_url=cover_url,
        )

        with timed(task_id, "mineru parse"):
            parse_result = await mineru.parse_pdf(title_id, pdf_bytes)
        parsed = parse_result.markdown
        content_list = parse_result.content_list
        logger.info(
            "[%s] parsed: %d chars; preview: %s...",
            task_id,
            len(parsed),
            parsed[:300],
        )

        with timed(task_id, "upload parsed.md + content_list.json"):
            await asyncio.to_thread(
                _upload, parsed_md_key, parsed.encode("utf-8"), "text/markdown"
            )
            await asyncio.to_thread(
                _upload,
                content_list_key,
                json.dumps(content_list).encode("utf-8"),
                "application/json",
            )

        if parse_result.images:
            with timed(task_id, f"upload {len(parse_result.images)} images"):
                await asyncio.gather(
                    *[
                        asyncio.to_thread(
                            _upload,
                            f"{images_prefix}/{name}",
                            data,
                            mimetypes.guess_type(name)[0] or "application/octet-stream",
                        )
                        for name, data in parse_result.images.items()
                    ]
                )

        await asyncio.to_thread(
            progress.update,
            uid,
            task_id,
            percent=PCT_PARSING_END,
            stage="vectorizing",
        )

        def _on_embed(frac: float) -> None:
            pct = PCT_PARSING_END + int(
                frac * (PCT_VECTORIZING_END - PCT_PARSING_END)
            )
            progress.update(uid, task_id, percent=pct, stage="vectorizing")

        with timed(task_id, "vectorize"):
            n_chunks = await vector_index.build(
                uid, title_id, content_list, on_progress=_on_embed
            )
        logger.info("[%s] vector index: %d chunks", task_id, n_chunks)

        await asyncio.to_thread(
            progress.update,
            uid,
            task_id,
            percent=PCT_VECTORIZING_END,
            stage="toc",
        )

        with timed(task_id, "toc extract"):
            toc_entries, toc_source = await asyncio.to_thread(
                toc.extract_toc, uid, title_id, content_list
            )
        logger.info(
            "[%s] toc: %d entries (source=%s)",
            task_id,
            len(toc_entries),
            toc_source,
        )

        with timed(task_id, "upload toc.json"):
            await asyncio.to_thread(
                _upload,
                toc_key,
                json.dumps([e.model_dump() for e in toc_entries]).encode("utf-8"),
                "application/json",
            )

        await asyncio.to_thread(
            progress.update, uid, task_id, percent=PCT_TOC_END, stage="writing"
        )

        with timed(task_id, "firestore write (final, isProcessing=false)"):
            await asyncio.to_thread(
                _write_title_doc,
                uid,
                title_id,
                fields={
                    "parsedMdKey": parsed_md_key,
                    "contentListKey": content_list_key,
                    "tocKey": toc_key,
                    "toc": [e.model_dump() for e in toc_entries],
                    "tocSource": toc_source,
                    "isProcessing": False,
                },
                merge=True,
            )

        await asyncio.to_thread(
            progress.update,
            uid,
            task_id,
            percent=PCT_DONE,
            stage="done",
            title_id=title_id,
        )

        total = time.perf_counter() - start
        logger.info(
            "[%s] /process total: %.2fs (title=%r, author=%r, toc=%d, chunks=%d)",
            task_id,
            total,
            meta.title,
            meta.author,
            len(toc_entries),
            n_chunks,
        )

    except Exception as exc:
        logger.exception("[%s] processing failed", task_id)
        await asyncio.to_thread(progress.fail, uid, task_id, str(exc))
        # If the title doc was already written, mark it failed too.
        try:
            await asyncio.to_thread(
                _write_title_doc,
                uid,
                title_id,
                fields={"isProcessing": False, "processingError": str(exc)},
                merge=True,
            )
        except Exception:
            pass
        # Re-raise so Cloud Tasks can retry per the queue's retry policy.
        raise
    finally:
        # Best-effort cleanup of the pending blob.
        try:
            await asyncio.to_thread(bucket.blob(source_key).delete)
        except Exception:
            pass
        # Schedule deletion of the progress doc 10s after terminal state so
        # the SSE client has a chance to receive the final event.
        asyncio.create_task(progress.delete_after_delay(uid, task_id))


def _write_title_doc(
    uid: str,
    title_id: str,
    *,
    fields: dict,
    merge: bool,
) -> None:
    ref = (
        firestore_client.collection("users")
        .document(uid)
        .collection("titles")
        .document(title_id)
    )
    if merge:
        ref.set(fields, merge=True)
    else:
        ref.set(fields)
