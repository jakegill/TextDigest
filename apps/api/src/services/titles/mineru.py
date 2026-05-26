import asyncio
import contextlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import google.auth
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from mineru.cli.common import do_parse

from ...dependencies import MINERU_URL
from .constants import GEMINI_3_5_FLASH, GEMINI_3_1_FLASH_LITE


@dataclass(slots=True)
class ParseResult:
    markdown: str
    content_list: list[dict]
    images: dict[str, bytes]


VERTEX_LOCATION = "us-central1"


def write_mineru_config() -> None:
    creds, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    project = project or os.environ["GOOGLE_CLOUD_PROJECT"]
    creds.refresh(GoogleRequest())
    title_aided = {
        "api_key": creds.token,
        "base_url": (
            f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com"
            f"/v1beta1/projects/{project}/locations/{VERTEX_LOCATION}"
            "/endpoints/openapi/"
        ),
        "model": f"google/{GEMINI_3_1_FLASH_LITE}",
        "enable": True,
    }
    cfg_path = os.environ.get("MINERU_TOOLS_CONFIG_JSON") or str(
        Path.home() / "mineru.json"
    )
    Path(cfg_path).write_text(
        json.dumps({"llm-aided-config": {"title_aided": title_aided}})
    )

    from mineru.backend.hybrid import hybrid_model_output_to_middle_json as _h
    _h.title_aided_config = title_aided
    _h.title_aided_enable = True


async def parse_pdf(
    title_id: str,
    pdf_bytes: bytes,
) -> ParseResult:
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
        root = Path(tmp) / title_id

        md_files = list(root.rglob(f"{title_id}.md"))
        if not md_files:
            raise RuntimeError(f"mineru wrote no {title_id}.md under {root}/")
        
        cl_files = list(root.rglob(f"{title_id}_content_list.json"))
        if not cl_files:
            raise RuntimeError(
                f"mineru wrote no {title_id}_content_list.json under {root}/"
            )
        content_list = json.loads(cl_files[0].read_text(encoding="utf-8"))

        images_dir = next(root.rglob("images"), None)
        images: dict[str, bytes] = {}
        if images_dir and images_dir.is_dir():
            for p in images_dir.iterdir():
                if p.is_file():
                    images[p.name] = p.read_bytes()

        return ParseResult(
            markdown=md_files[0].read_text(encoding="utf-8"),
            content_list=content_list,
            images=images,
        )
