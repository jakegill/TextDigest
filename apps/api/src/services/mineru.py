import asyncio
import json
import os
import tempfile
from pathlib import Path

import google.auth
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from mineru.cli.common import do_parse

from ..dependencies import MINERU_URL

VERTEX_LOCATION = "us-central1"
GEMINI_MODEL = "google/gemini-2.5-flash"
LLM_AIDED_SECTIONS = ("title_aided", "text_aided", "formula_aided")


def write_mineru_config() -> None:
    creds, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    project = project or os.environ["GOOGLE_CLOUD_PROJECT"]
    creds.refresh(GoogleRequest())
    base_url = (
        f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com"
        f"/v1beta1/projects/{project}/locations/{VERTEX_LOCATION}/endpoints/openapi/"
    )
    config = {
        "llm-aided-config": {
            section: {
                "api_key": creds.token,
                "base_url": base_url,
                "model": GEMINI_MODEL,
                "enable": True,
            }
            for section in LLM_AIDED_SECTIONS
        }
    }
    cfg_path = os.environ.get("MINERU_TOOLS_CONFIG_JSON") or str(
        Path.home() / "mineru.json"
    )
    Path(cfg_path).write_text(json.dumps(config))


async def parse_pdf(title_id: str, pdf_bytes: bytes) -> str:
    os.environ["MINERU_VL_API_KEY"] = id_token.fetch_id_token(
        GoogleRequest(), MINERU_URL
    )
    write_mineru_config()

    with tempfile.TemporaryDirectory() as tmp:
        await asyncio.to_thread(
            do_parse,
            output_dir=tmp,
            pdf_file_names=[title_id],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=["en"],
            backend="hybrid-http-client",
            server_url=MINERU_URL,
        )
        md_files = list((Path(tmp) / title_id).rglob(f"{title_id}.md"))
        if not md_files:
            raise RuntimeError(f"mineru wrote no {title_id}.md under {tmp}/{title_id}/")
        return md_files[0].read_text(encoding="utf-8")
