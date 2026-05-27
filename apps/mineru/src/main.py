import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

import google.auth
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from google.auth.transport.requests import Request as GoogleRequest
from google.cloud import storage
from google.cloud.storage import transfer_manager
from mineru.backend.hybrid import hybrid_model_output_to_middle_json as _h
from mineru.cli.common import do_parse

# set in infra/gpu.ts
DATA_BUCKET = os.environ["DATA_BUCKET"]
PROJECT_ID = os.environ["PROJECT_ID"]

TITLE_AIDED_MODEL = "gemini-3.1-flash-lite"
VERTEX_LOCATION = "global"

logger = logging.getLogger("mineru")
logging.basicConfig(level=logging.INFO)

app = FastAPI()
gcs_client = storage.Client()


def _configure_title_aided() -> None:
    """Mint a fresh Vertex access token and wire it into mineru's hybrid backend.

    The token lives ~1 hour. Refresh per parse since parses are infrequent and
    long-lived (multi-minute), so reusing a cached token across parses risks
    expiry mid-call.
    """
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(GoogleRequest())
    title_aided = {
        "api_key": creds.token,
        "base_url": (
            "https://aiplatform.googleapis.com"
            f"/v1beta1/projects/{PROJECT_ID}/locations/{VERTEX_LOCATION}"
            "/endpoints/openapi/"
        ),
        "model": f"google/{TITLE_AIDED_MODEL}",
        "enable": True,
    }
    _h.title_aided_config = title_aided
    _h.title_aided_enable = True


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/parse")
async def parse(
    pdf: UploadFile = File(...),
    title_id: str = Form(...),
    images_prefix: str = Form(...),
    lang: str = Form("en"),
) -> dict:
    """Parse a PDF and stream extracted images to GCS.

    `images_prefix` is the GCS key prefix (no leading slash, no trailing slash)
    where the api wants images deposited — the caller owns the storage layout,
    not us. Final paths are `gs://${DATA_BUCKET}/${images_prefix}/${filename}`.
    """
    pdf_bytes = await pdf.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="empty pdf")

    _configure_title_aided()

    with tempfile.TemporaryDirectory() as tmp:
        do_parse(
            output_dir=tmp,
            pdf_file_names=[title_id],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=[lang],
            backend="hybrid-auto-engine",
        )
        root = Path(tmp) / title_id

        md_files = list(root.rglob(f"{title_id}.md"))
        if not md_files:
            raise HTTPException(
                status_code=500, detail=f"mineru wrote no {title_id}.md"
            )
        markdown = md_files[0].read_text(encoding="utf-8")

        cl_files = list(root.rglob(f"{title_id}_content_list.json"))
        if not cl_files:
            raise HTTPException(
                status_code=500,
                detail=f"mineru wrote no {title_id}_content_list.json",
            )
        content_list = json.loads(cl_files[0].read_text(encoding="utf-8"))

        images_dir = next(root.rglob("images"), None)
        if images_dir and images_dir.is_dir():
            bucket = gcs_client.bucket(DATA_BUCKET)
            filenames = [p.name for p in images_dir.iterdir() if p.is_file()]
            if filenames:
                await asyncio.to_thread(
                    transfer_manager.upload_many_from_filenames,
                    bucket,
                    filenames,
                    source_directory=str(images_dir),
                    blob_name_prefix=f"{images_prefix}/",
                    worker_type=transfer_manager.THREAD,
                    max_workers=16,
                    raise_exception=True,
                )
                logger.info("uploaded %d images to %s", len(filenames), images_prefix)

    return {"markdown": markdown, "content_list": content_list}
