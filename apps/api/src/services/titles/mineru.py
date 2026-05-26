from dataclasses import dataclass

import httpx
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from ...dependencies import MINERU_URL


@dataclass(slots=True)
class ParseResult:
    markdown: str
    content_list: list[dict]


async def parse_pdf(
    title_id: str,
    pdf_bytes: bytes,
    images_prefix: str,
) -> ParseResult:
    # Cloud Run OIDC bearer token authorizes the call; api-sa has run.invoker
    # on the mineru service (see infra/cpu.ts api-invokes-mineru).
    # `images_prefix` tells mineru where to write extracted images in the
    # shared data bucket — caller owns the layout.
    token = id_token.fetch_id_token(GoogleRequest(), MINERU_URL)
    async with httpx.AsyncClient(timeout=900.0) as client:
        r = await client.post(
            f"{MINERU_URL}/parse",
            headers={"Authorization": f"Bearer {token}"},
            files={"pdf": (title_id, pdf_bytes, "application/pdf")},
            data={
                "title_id": title_id,
                "images_prefix": images_prefix,
                "lang": "en",
            },
        )
        r.raise_for_status()
        payload = r.json()
    return ParseResult(
        markdown=payload["markdown"],
        content_list=payload["content_list"],
    )
