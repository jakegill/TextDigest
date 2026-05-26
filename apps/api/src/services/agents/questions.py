import re
from typing import AsyncIterator
from urllib.parse import unquote, urlparse

from google import genai
from google.genai import types
from loguru import logger

from ...dependencies import PROJECT_ID
from .constants import GEMINI_3_5_FLASH, GEMINI_3_1_FLASH_LITE

VERTEX_LOCATION = "global"
MAX_IMAGES_PER_TURN = 6

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)

_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(\s*([^\s)]+)(?:\s+\"[^\"]*\")?\s*\)")
_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _extract_image_urls(md: str) -> list[str]:
    return _MD_IMG_RE.findall(md)


def _strip_md_images(md: str) -> str:
    return _MD_IMG_RE.sub("", md)


def _signed_https_to_gs(url: str) -> str | None:
    try:
        p = urlparse(url)
        if p.netloc != "storage.googleapis.com":
            return None
        path = unquote(p.path).lstrip("/")
        bucket, _, key = path.partition("/")
        if not bucket or not key:
            return None
        return f"gs://{bucket}/{key}"
    except Exception:
        return None


def _guess_mime(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext, mime in _MIME_BY_EXT.items():
        if path.endswith(ext):
            return mime
    return "image/jpeg"


def _system_prompt(
    title: str,
    author: str,
    page_content: str,
    highlighted_text: str,
    has_images: bool,
) -> str:
    image_workflow = (
        "- Reference the attached page images when relevant to the question.\n"
        if has_images
        else ""
    )
    image_hint = (
        "Images from the user's current page are attached in the user turn. "
        "Use them along with the text context when answering.\n\n"
        if has_images
        else ""
    )
    return f"""\
# Persona
You are a useful study assistant. The user is reading an e-book and wants you to clarify or expand on the highlighted portion of text, or to answer a general question about the current page.

# Workflow
- Use the highlighted text and user query as the foundation for your response.
- Use the surrounding e-book page content for further context.
- Use the book title and author for broader context.
{image_workflow}
# Context
<book title>
{title}
</book title>

<book author>
{author}
</book author>

<current ebook page content>
{page_content}
</current ebook page content>

<highlighted text>
{highlighted_text}
</highlighted text>

{image_hint}# Expected Response
A concise answer to the user's question."""


async def stream_answer(
    *,
    query: str,
    highlighted_text: str,
    page_content: str,
    title: str,
    author: str,
    history: list[dict],
) -> AsyncIterator[str]:
    image_urls = _extract_image_urls(page_content)
    page_text = _strip_md_images(page_content)
    system = _system_prompt(title, author, page_text, highlighted_text, has_images=bool(image_urls))

    contents: list[types.ContentUnion] = []
    for turn in history:
        role = "model" if turn.get("role") == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=turn.get("content", ""))])
        )

    current_parts: list[types.Part] = []
    images_sent = 0
    for url in image_urls:
        if images_sent >= MAX_IMAGES_PER_TURN:
            break
        gs_uri = _signed_https_to_gs(url)
        if not gs_uri:
            continue
        current_parts.append(types.Part.from_uri(file_uri=gs_uri, mime_type=_guess_mime(url)))
        images_sent += 1
    current_parts.append(types.Part.from_text(text=query))
    contents.append(types.Content(role="user", parts=current_parts))

    logger.info(
        f"[questions] turn: query_chars={len(query)} highlighted_chars={len(highlighted_text)} "
        f"page_text_chars={len(page_text)} images_found={len(image_urls)} images_sent={images_sent}"
    )

    stream = await _client.aio.models.generate_content_stream(
        model=GEMINI_3_5_FLASH,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text


async def generate_title(first_message: str) -> str:
    resp = await _client.aio.models.generate_content(
        model=GEMINI_3_1_FLASH_LITE,
        contents=f"""\
        Generate a 3-5 word title summarizing this user question. 
        Output the title only — no quotes, no trailing punctuation.

        Question: {first_message}""",
    )
    cleaned = (resp.text or "").strip().strip('"').strip()[:80]
    return cleaned or "Untitled"
