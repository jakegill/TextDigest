from typing import AsyncIterator

from google import genai
from google.genai import types

from ...dependencies import PROJECT_ID
from .constants import GEMINI_3_FLASH_PREVIEW

VERTEX_LOCATION = "global"

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


def _system_prompt(title: str, author: str, page_content: str, highlighted_text: str) -> str:
    return (
        "# Persona\n"
        "You are a useful study assistant. The user is reading an e-book and "
        "wants you to clarify or expand on the highlighted portion of text, "
        "or to answer a general question about the current page.\n\n"
        "# Workflow\n"
        "- Use the highlighted text and user query as the foundation for your response.\n"
        "- Use the surrounding e-book page content for further context.\n"
        "- Use the book title and author for broader context.\n\n"
        "# Context\n"
        f"<book title>\n{title}\n</book title>\n\n"
        f"<book author>\n{author}\n</book author>\n\n"
        f"<current ebook page content>\n{page_content}\n</current ebook page content>\n\n"
        f"<highlighted text>\n{highlighted_text}\n</highlighted text>\n\n"
        "# Expected Response\n"
        "A concise answer to the user's question."
    )


async def stream_answer(
    *,
    query: str,
    highlighted_text: str,
    page_content: str,
    title: str,
    author: str,
    history: list[dict],
) -> AsyncIterator[str]:
    system = _system_prompt(title, author, page_content, highlighted_text)

    contents: list[types.Content] = []
    for turn in history:
        role = "model" if turn.get("role") == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=turn.get("content", ""))])
        )
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=query)]))

    stream = await _client.aio.models.generate_content_stream(
        model=GEMINI_3_FLASH_PREVIEW,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text


async def generate_title(first_message: str) -> str:
    resp = await _client.aio.models.generate_content(
        model=GEMINI_3_FLASH_PREVIEW,
        contents=(
            "Generate a 3-5 word title summarizing this user question. "
            "Output the title only — no quotes, no trailing punctuation.\n\n"
            f"Question: {first_message}"
        ),
    )
    cleaned = (resp.text or "").strip().strip('"').strip()[:80]
    return cleaned or "Untitled"
