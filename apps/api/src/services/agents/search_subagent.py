"""Search subagent: single Gemini call with google_search, returns a clean URL list.

No browser, no CAPTCHA risk — google_search is Gemini's built-in grounding tool;
the SERP never enters our pipeline.
"""

import asyncio
import logging
from typing import Any

import httpx
from google import genai
from google.genai import types

from ...dependencies import PROJECT_ID
from .constants import GEMINI_2_5_FLASH

logger = logging.getLogger("uvicorn.error")

VERTEX_LOCATION = "us-central1"
_GROUNDING_REDIRECT_PREFIX = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
_UNWRAP_TIMEOUT_S = 4.0

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


async def _unwrap_url(client: httpx.AsyncClient, url: str) -> str:
    """Resolve Google's grounding-api-redirect wrapper to the canonical URL.
    Only ever connects to Google; reads the Location header without following
    the redirect, so destination-side anti-bot never sees us."""
    if not url.startswith(_GROUNDING_REDIRECT_PREFIX):
        return url
    try:
        r = await client.get(url, follow_redirects=False, timeout=_UNWRAP_TIMEOUT_S)
        if r.is_redirect and "location" in r.headers:
            canonical = str(httpx.URL(url).join(r.headers["location"]))
            logger.info("[search_subagent] unwrapped → %s", canonical)
            return canonical
        return url
    except httpx.HTTPError as e:
        logger.info(
            "[search_subagent] unwrap failed url=%s… error=%s",
            url[:80], e.__class__.__name__,
        )
        return url


async def search(query: str, count: int = 10) -> list[dict[str, str]]:
    """Returns [{title, url, snippet}, ...]. Uses gemini-2.5-flash + google_search."""
    prompt = (
        f"Run a Google search for: {query}\n\n"
        f"Return the top {count} results as found by the search engine. "
        "Do not pre-filter, do not judge accessibility — just return what Google returned."
    )
    response = await _client.aio.models.generate_content(
        model=GEMINI_2_5_FLASH,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    if response.candidates:
        gm = response.candidates[0].grounding_metadata
        chunks = (gm.grounding_chunks or []) if gm else []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if not web:
                continue
            url = (web.uri or "").strip()
            title = (web.title or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({"title": title, "url": url, "snippet": ""})

    results = results[:count]

    async with httpx.AsyncClient() as client:
        unwrapped = await asyncio.gather(
            *(_unwrap_url(client, r["url"]) for r in results)
        )
    for r, c in zip(results, unwrapped):
        r["url"] = c

    logger.info(
        "[search_subagent] query=%r returned=%d", query, len(results)
    )
    return results


def _result_summary_for_log(results: list[dict[str, str]], max_items: int = 5) -> list[Any]:
    return [
        {"title": r["title"][:60], "url": r["url"]}
        for r in results[:max_items]
    ]
