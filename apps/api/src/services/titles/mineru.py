import asyncio
import json

import httpx
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from ...dependencies import MINERU_URL, bucket


async def parse_pdf(
    title_id: str,
    source_key: str,
    images_prefix: str,
    parsed_md_key: str,
    content_list_key: str,
) -> list[dict]:
    # Cloud Run OIDC bearer token authorizes the call; api-sa has run.invoker
    # on the mineru service (see infra/cpu.ts api-invokes-mineru).
    # The request and response carry only GCS keys — Cloud Run caps HTTP/1
    # bodies at 32 MiB in both directions, so mineru reads the source PDF
    # from the shared data bucket and writes parsed.md + content_list.json
    # back to it. Caller owns the storage layout.
    token = id_token.fetch_id_token(GoogleRequest(), MINERU_URL)
    async with httpx.AsyncClient(timeout=900.0) as client:
        r = await client.post(
            f"{MINERU_URL}/parse",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "source_key": source_key,
                "title_id": title_id,
                "images_prefix": images_prefix,
                "parsed_md_key": parsed_md_key,
                "content_list_key": content_list_key,
                "lang": "en",
            },
        )
        r.raise_for_status()
    raw = await asyncio.to_thread(bucket.blob(content_list_key).download_as_bytes)
    return json.loads(raw.decode("utf-8"))
