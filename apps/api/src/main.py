import asyncio
import base64
import json
import logging
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.auth.transport.requests import Request as GoogleRequest
from google.cloud import storage
from google.oauth2 import id_token
from mineru.cli.common import do_parse

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="text-digest-v2 api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MINERU_URL = os.environ["MINERU_URL"]
DATA_BUCKET = os.environ["DATA_BUCKET"]
storage_client = storage.Client()
bucket = storage_client.bucket(DATA_BUCKET)


@contextmanager
def timed(title_id: str, step: str) -> Iterator[None]:
    logger.info("[%s] %s...", title_id, step)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        logger.info("[%s] %s done in %.2fs", title_id, step, time.perf_counter() - t0)


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        logger.info("id token: %s", token)
        parts = token.split(".")
        if len(parts) >= 2:
            # Base64url-decode the JWT payload (no signature verification).
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_b64))
            logger.info("token claims:\n%s", json.dumps(claims, indent=2))
    return {"status": "ok"}


@app.post("/titles")
async def upload_title(file: UploadFile) -> dict[str, object]:
    pdf_bytes = await file.read()
    title_id = str(uuid.uuid4())
    pdf_kb = len(pdf_bytes) / 1024
    logger.info(
        "[%s] upload received: %s (%.1f KB)", title_id, file.filename, pdf_kb
    )

    request_start = time.perf_counter()

    with timed(title_id, "upload source.pdf → gcs"):
        bucket.blob(f"titles/{title_id}/source.pdf").upload_from_string(
            pdf_bytes, content_type="application/pdf"
        )

    with timed(title_id, "fetch oidc token for mineru"):
        os.environ["MINERU_VL_API_KEY"] = id_token.fetch_id_token(
            GoogleRequest(), MINERU_URL
        )

    with tempfile.TemporaryDirectory() as tmp:
        with timed(title_id, "mineru do_parse (vlm-http-client)"):

            await asyncio.to_thread(
                do_parse,
                output_dir=tmp,
                pdf_file_names=[title_id],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=["en"],
                backend="hybrid-http-client",
                server_url=MINERU_URL,
            )

        with timed(title_id, "read parsed.md from tmp"):
            md_files = list((Path(tmp) / title_id).rglob(f"{title_id}.md"))
            if not md_files:
                raise RuntimeError(f"mineru wrote no {title_id}.md under {tmp}/{title_id}/")
            parsed = md_files[0].read_text(encoding="utf-8")

    logger.info(
        "[%s] parsed: %d chars; preview: %s...", title_id, len(parsed), parsed[:300]
    )

    with timed(title_id, "upload parsed.md → gcs"):
        bucket.blob(f"titles/{title_id}/parsed.md").upload_from_string(
            parsed, content_type="text/markdown"
        )

    total = time.perf_counter() - request_start
    logger.info("[%s] /titles total: %.2fs", title_id, total)

    return {"titleId": title_id, "previewChars": len(parsed)}
