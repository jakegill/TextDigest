"""Orchestrator agent for the Find-a-Title feature.

Three-agent architecture:
  - Orchestrator (this file): gemini-3.5-flash + two function_declarations.
    Pure router — picks research vs. find based on user intent.
  - Research subagent (research_subagent.py): gemini-3.5-flash + google_search.
    Returns curated markdown of expert-recommended titles on a topic.
  - Find subagent (find_subagent.py): owns the entire search→verify→retry
    pipeline for a specific named book. Wraps search_subagent +
    verification_subagent internally.
"""

import logging
import time
import uuid
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from ...dependencies import PROJECT_ID
from . import find_subagent, research_subagent
from .constants import GEMINI_3_5_FLASH

logger = logging.getLogger("uvicorn.error")

VERTEX_LOCATION = "global"
_MAX_ORCHESTRATOR_STEPS = 6

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)

SYSTEM_PROMPT_BASE = """\

You are the conversational orchestrator for a book-discovery tool. The user chats with you; you route their requests to subagents that do the actual work.

**You have NO direct web access.** You cannot browse URLs, search the web, fetch external content, or look anything up yourself.

# Workflow
- Your task is to route the user's request to the right subagent.
- You are not conversational — unless the user explicitly asks something out of scope of the subagents.

## Immediate Response Workflow
- Clarifying questions back to the user ('which one did you mean?', 'do you want a PDF or just the title?')
- Questions about prior turns in this conversation ('the third book I recommended was X' — when you actually said that earlier)

## Delegation Workflow
- Topical reading / recommendations / curated lists ('books on X', 'what should I read about Y', 'Karpathy's reading list') → call `research(topic)`.
- Specific named book the user wants a PDF of ('find me Information Dashboard Design by Stephen Few', 'get me Goodfellow's Deep Learning textbook') → call `find(title, author)`.

### Subagents
- `research(topic)`: surveys reddit, blogs, expert posts, syllabi. Returns curated MARKDOWN streamed live to the user. Use for ANY recommendation / reading-list / 'what does X say about Y' question.
- `find(title, author)`: drives the entire search→verify pipeline internally. Parse the user's request into title + author (author may be empty if not given) and call it ONCE. The subagent emits its own progress events and a `candidates` block when done; you do not need to do anything else after calling it.

# After research()
The subagent STREAMS the markdown LIVE to the user. After research() returns, emit NO further text — do not repeat, summarize, restate, or add commentary. End your turn immediately.

# After find()
The subagent emits its own progress and a candidates block live. After find() returns, end your turn immediately with no further text.

# Be concise
Don't narrate every decision. The user sees subagent events live."""


def _library_block(existing: list[dict[str, str]]) -> str:
    if not existing:
        return ""
    rows = "\n".join(
        f"- {e.get('title', '').strip()} — {e.get('author', '').strip()}"
        for e in existing
        if (e.get("title") or "").strip()
    )
    if not rows:
        return ""
    return (
        "\n\n# User's existing library\n"
        "Avoid recommending any title already in this list:\n"
        f"{rows}"
    )


def _find_declaration() -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name="find",
        description=(
            "Find a free PDF of a specific named book. Drives a multi-step "
            "search→verify pipeline internally and emits a candidates block "
            "when done. Use ONLY when the user names a specific book. Parse "
            "the request into title + author (author may be empty if the user "
            "didn't give one)."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "title": types.Schema(type=types.Type.STRING),
                "author": types.Schema(type=types.Type.STRING),
            },
            required=["title"],
        ),
    )


def _research_declaration() -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name="research",
        description=(
            "Research book recommendations on a topic by searching reddit, blogs, "
            "expert sources, and course syllabi. Use ONLY when the user has not "
            "named a specific book — i.e. they describe a topic or interest "
            "('books on X', 'I want to learn about Y'). Returns curated markdown "
            "of 3-7 recommendations the user can then ask you to find. Do NOT use "
            "for queries that name a specific title."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "topic": types.Schema(type=types.Type.STRING),
            },
            required=["topic"],
        ),
    )


async def stream_search(
    query: str,
    uid: str,
    existing: list[dict[str, str]] | None = None,
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    sid = uuid.uuid4().hex[:8]
    logger.info(
        "[orchestrator sid=%s] START uid=%s query=%r library_size=%d history_turns=%d max_steps=%d",
        sid, uid, query, len(existing or []), len(history or []), _MAX_ORCHESTRATOR_STEPS,
    )

    system_instruction = SYSTEM_PROMPT_BASE + _library_block(existing or [])

    contents: list[types.ContentUnion] = []
    for turn in history or []:
        role = "model" if turn.get("role") == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=turn.get("content", ""))])
        )
    contents.append(types.Content(role="user", parts=[types.Part(text=query)]))

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.7,
        max_output_tokens=4096,
        tools=[
            types.Tool(
                function_declarations=[
                    _research_declaration(),
                    _find_declaration(),
                ]
            ),
        ],
    )

    start = time.monotonic()

    for step in range(1, _MAX_ORCHESTRATOR_STEPS + 1):
        model_t0 = time.monotonic()
        text_parts: list[str] = []
        function_calls: list[types.FunctionCall] = []
        model_parts: list[types.Part] = []
        try:
            async for chunk in await _client.aio.models.generate_content_stream(
                model=GEMINI_3_5_FLASH,
                contents=contents,
                config=config,
            ):
                if not chunk.candidates:
                    continue
                cand = chunk.candidates[0]
                if not (cand.content and cand.content.parts):
                    continue
                for part in cand.content.parts:
                    model_parts.append(part)
                    if part.text:
                        text_parts.append(part.text)
                        yield {"event": "thinking", "body": part.text}
                    if part.function_call:
                        function_calls.append(part.function_call)
        except Exception as e:
            logger.exception(
                "[orchestrator sid=%s] generate_content failed step=%d", sid, step
            )
            yield {"event": "error", "body": f"model error: {e}"}
            return
        model_ms = (time.monotonic() - model_t0) * 1000

        if model_parts:
            contents.append(types.Content(role="model", parts=model_parts))

        logger.info(
            "[orchestrator sid=%s] step=%d model_ms=%.0f text_chars=%d calls=%d names=%s",
            sid, step, model_ms, sum(len(t) for t in text_parts), len(function_calls),
            [fc.name for fc in function_calls],
        )

        if not function_calls:
            logger.info(
                "[orchestrator sid=%s] STOP reason=agent_done step=%d elapsed=%.1fs",
                sid, step, time.monotonic() - start,
            )
            return

        function_responses: list[types.FunctionResponse] = []

        for fc in function_calls:
            args = fc.args or {}
            name = fc.name
            if name == "research":
                topic = str(args.get("topic") or "")
                yield {
                    "event": "subagent_call",
                    "body": {"agent": "research", "input": {"topic": topic}},
                }
                yield {"event": "research_chunk", "body": "\n\n"}
                t0 = time.monotonic()
                accumulated: list[str] = []
                try:
                    async for delta in research_subagent.research_stream(topic):
                        accumulated.append(delta)
                        yield {"event": "research_chunk", "body": delta}
                except Exception as e:
                    logger.exception(
                        "[orchestrator sid=%s] research subagent failed topic=%r",
                        sid, topic,
                    )
                    function_responses.append(
                        types.FunctionResponse(
                            id=fc.id,
                            name="research",
                            response={"error": str(e), "delivered_to_user": False},
                        )
                    )
                    continue
                logger.info(
                    "[orchestrator sid=%s] research done topic=%r chars=%d ms=%.0f",
                    sid, topic, sum(len(d) for d in accumulated),
                    (time.monotonic() - t0) * 1000,
                )
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name="research",
                        response={
                            "delivered_to_user": True,
                            "topic": topic,
                            "instruction": (
                                "The full markdown recommendations have already been "
                                "streamed live to the user. Do NOT repeat, summarize, "
                                "or restate any of the content in your response. End "
                                "your turn now with no further text."
                            ),
                        },
                    )
                )
            elif name == "find":
                title = str(args.get("title") or "").strip()
                author = str(args.get("author") or "").strip()
                if not title:
                    logger.warning(
                        "[orchestrator sid=%s] find rejected: empty title", sid,
                    )
                    function_responses.append(
                        types.FunctionResponse(
                            id=fc.id,
                            name="find",
                            response={"error": "title is required"},
                        )
                    )
                    continue
                logger.info(
                    "[orchestrator sid=%s] find delegating title=%r author=%r",
                    sid, title, author,
                )
                t0 = time.monotonic()
                candidate_count = 0
                try:
                    async for ev in find_subagent.stream_find(title, author, uid):
                        if ev.get("event") == "candidates":
                            body = ev.get("body") or []
                            candidate_count = len(body) if isinstance(body, list) else 0
                        yield ev
                except Exception as e:
                    logger.exception(
                        "[orchestrator sid=%s] find subagent failed title=%r author=%r",
                        sid, title, author,
                    )
                    yield {"event": "error", "body": f"find error: {e}"}
                logger.info(
                    "[orchestrator sid=%s] find done title=%r candidates=%d ms=%.0f",
                    sid, title, candidate_count, (time.monotonic() - t0) * 1000,
                )
                # find is terminal: end the orchestrator turn here.
                logger.info(
                    "[orchestrator sid=%s] STOP reason=find_done elapsed=%.1fs",
                    sid, time.monotonic() - start,
                )
                return
            else:
                logger.warning(
                    "[orchestrator sid=%s] unknown function call name=%s", sid, name
                )
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name=name or "unknown",
                        response={"error": "unknown function"},
                    )
                )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(function_response=fr) for fr in function_responses],
            )
        )

    logger.info(
        "[orchestrator sid=%s] STOP reason=step_budget steps=%d elapsed=%.1fs",
        sid, _MAX_ORCHESTRATOR_STEPS, time.monotonic() - start,
    )
    # Step budget exhausted without a terminal call — surface an empty
    # candidates so the frontend stops its spinner.
    yield {"event": "candidates", "body": []}
