"""Research subagent: scours web for expert book recommendations on a topic."""

import logging
from typing import AsyncIterator

from google import genai
from google.genai import types

from ...dependencies import PROJECT_ID
from .constants import GEMINI_2_5_FLASH

logger = logging.getLogger("uvicorn.error")

VERTEX_LOCATION = "us-central1"
_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)

_RESEARCH_PROMPT = """You research book recommendations on a topic.

Topic: {topic}

Search the web for:
- Reddit threads ("what's the best book on X", r/<relevant subreddit> recommendations)
- Blog posts and "best of" lists from credible practitioners in the space
- Opinions and recommendations from recognized leaders / authors in the field
- Course syllabi from well-regarded university programs

Return a curated list of 3-7 book recommendations as MARKDOWN with this exact shape:

## Recommended reads on {topic}

### 1. <Book title> — <Author>
**Why it's recommended:** <one sentence citing the source of the recommendation, e.g. "Top-voted in r/MachineLearning's 'best books' thread; Andrew Ng cites it in his syllabus.">
**Synopsis:** <one to two sentences describing what the book covers and its angle.>

### 2. ...

Pick recommendations that real experts actually cite — not just whatever Google ranks. Prefer canonical / widely-recommended over obscure. Keep titles to ones that are likely to have publicly accessible PDFs (textbooks, classic books, open-access editions), since the user will try to add them to their library next.
"""


async def research_stream(topic: str) -> AsyncIterator[str]:
    """Yields text deltas as the model generates the markdown recommendations."""
    total = 0
    async for chunk in await _client.aio.models.generate_content_stream(
        model=GEMINI_2_5_FLASH,
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
