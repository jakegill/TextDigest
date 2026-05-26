"""Research subagent: scours web for expert book recommendations on a topic."""

import logging
from typing import AsyncIterator

from google import genai
from google.genai import types

from ...dependencies import PROJECT_ID
from .constants import GEMINI_3_5_FLASH

logger = logging.getLogger("uvicorn.error")

VERTEX_LOCATION = "global"
_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)

_RESEARCH_PROMPT = """
You are an AI assistant embedded into an e-readers library page whose sole task is to 
research a reading list on a topic by surveying what authoritative figures in the field actually point to.

Topic: {topic}

# Workflow 
Search the web for what these sources recommend on this topic — prioritize signal over volume:
- Search term user provided if relevant
- Professional communities specific to the domain (high-signal subreddits, Hacker News threads, domain-specific forums, Stack Exchange "what to read" answers)
- Course syllabi from well-regarded university or graduate programs covering the topic
- Reading lists or "books I recommend" pages from respected individuals shaping the field (X.com, researchers, authors, longtime practitioners, founders)
- Citations and bibliographies in seminal papers, canonical posts, or widely-watched talks on the topic

A book belongs on the list only when at least one credible authority can be cited as recommending it and it is relevant to the users conversation. 
Only include what can be found online as books, we do not want video courses, lectures, or other non-book forms of

# Output
Markdown representing the reading list. Let the topic dictate the length — three rock-solid titles beat ten weak ones, but include more if the topic genuinely has more well-attested resources. Quality over quantity.

## Style
- Avoid filler words; dont drop information but be concise.

## Ranking
- List titles by quality, (but dont mention that or number them conversationally)

## Format
**<Title>** by <Author>
- where the recommendation comes from (name the specific person, syllabus, or community thread)
- 1 bullet point on why this book is relevant and/or useful.
"""


async def research_stream(topic: str) -> AsyncIterator[str]:
    """Yields text deltas as the model generates the markdown recommendations."""
    total = 0
    async for chunk in await _client.aio.models.generate_content_stream(
        model=GEMINI_3_5_FLASH,
        contents=_RESEARCH_PROMPT.format(topic=topic),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.4,
        ),
    ):
        text = chunk.text
        if text:
            total += len(text)
            yield text
    logger.info("[research_subagent] topic=%r chars=%d", topic, total)
