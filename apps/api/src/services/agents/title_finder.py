"""Orchestrator agent for the Find-a-Title feature.

Four-agent architecture:
  - Orchestrator (this file): gemini-3.5-flash + three function_declarations.
    Routes each turn between research mode and find mode.
  - Research subagent (research_subagent.py): gemini-3.5-flash + google_search.
    Returns curated markdown of expert-recommended titles on a topic.
  - Search subagent (search_subagent.py): gemini-3.5-flash + google_search
    built-in tool. One call per invocation, returns URLs.
  - Verification subagent (verification_subagent.py): gemini-2.5-computer-use-
    preview + PlaywrightComputer. Full browser-driven verification of a single URL.

Each subagent uses exactly ONE tool kind so no tool-combination edge cases.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from ...dependencies import PROJECT_ID
from . import research_subagent, search_subagent, verification_subagent
from .constants import GEMINI_3_5_FLASH

logger = logging.getLogger("uvicorn.error")

VERTEX_LOCATION = "global"
_MAX_ORCHESTRATOR_STEPS = 20

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)

SYSTEM_PROMPT_BASE = """\
# Persona
You are the conversational orchestrator for a book-discovery tool. The user chats with you; you route their requests to subagents that do the actual web work.

**You have NO direct web access.** You cannot browse URLs, search the web, fetch external content, or look anything up yourself. If the answer isn't already in this chat history, you MUST delegate to a subagent. NEVER say 'I cannot browse', 'you can find it at <URL>', or apologize for lacking access — instead, delegate. The subagents have the web access you lack.

# What you CAN answer directly (no tool call)
- Clarifying questions back to the user ('which one did you mean?', 'do you want a PDF or just the title?')
- Questions about prior turns in this conversation ('the third book I recommended was X' — when you actually said that earlier)
- A brief sentence narrating what you're about to do BEFORE calling a subagent (see 'Narrate before each tool call' below)

# What you MUST delegate (do NOT answer yourself)
Anything that needs information from outside this conversation. Examples:
- Topical reading: 'books on X', 'what should I read about Y', 'best books on Z'
- Curated lists / expert recommendations: 'what's on Karpathy's reading list', 'what does Goodfellow recommend', 'what books does the LessWrong community like'
- Follow-ups to a prior research turn that need more info ('elaborate on his deep learning picks', 'what does he recommend for beginners') — call research() again with a more specific topic
→ All of the above: call research(topic).

- Finding a specific named book as a PDF ('find me Grokking Deep Learning', 'get the Goodfellow book')
→ Use search() + verify() per the workflow below.

# Subagents
- research(topic): web-research subagent. Surveys reddit, blogs, expert posts, syllabi. Returns curated MARKDOWN streamed live to the user. Use for ANY recommendation / reading-list / 'what does X say about Y' question.
- search(query): Google search subagent. Returns {title, url, snippet}. Use ONLY for finding a specific named book.
- verify(url, expected_title): browser subagent that actually loads the URL and confirms it serves the full book PDF. Returns {ok, resolvedUrl, reason}.

# Narrate before each tool call
Before calling a subagent, emit ONE short sentence telling the user what you're about to do. Examples:
  'Let me put together a reading list on that.'
  'I'll look up what's on Karpathy's recommended reads.'
  'Searching for that book now.'
Then call the subagent in the same turn. Keep it to one sentence — the user sees subagent activity live.

# After research()
The subagent STREAMS the markdown LIVE to the user. After research() returns, emit NO further text — do not repeat, summarize, restate, or add commentary. End your turn immediately. The user reads the streamed markdown and replies in their next turn.

# Workflow (specific-book find flow)
1. Call search() with a query like `<title> <author> free pdf` or, if the user asked topically ("books about X"), first search for `books about <topic>` to discover candidate titles, then search per title.
2. From the search results, pick 3-5 promising URLs. Skip obvious paywall/login hosts (researchgate.net, scribd.com, academia.edu, libgen, z-lib, dokumen.pub, epdf.pub, download-book.com).
3. Call verify(url, expected_title) on ALL picks IN PARALLEL (emit multiple verify function calls in one turn). Parallel is much faster when some URLs are bad — and the dispatcher will cancel the remaining verifies as SOON as one returns ok=true with the full book.
4. You only need ONE verified full PDF. When you get an ok=true result, that's it — emit the <candidates> block with that ONE candidate and stop:
   <candidates>[{"title":..., "author":..., "sourceUrl":..., "snippet":...}]</candidates>
   Use the RESOLVED url from verify() as sourceUrl.
5. If ALL verifies came back ok=false (every URL was a preview/paywall/dead): pick more URLs from the same search results and verify them, OR call search() with a MEANINGFULLY DIFFERENT query (see rule 6).
6. Search queries MUST vary along a real axis — do NOT just rephrase the same intent (e.g. 'X free pdf' → 'X full book pdf' is NOT meaningful variation; Google returns the same SERP). Pick a different axis each retry:
   - Add the author name (e.g. 'Grokking Deep Learning Andrew Trask pdf')
   - Add edition or year (e.g. 'X 2nd edition pdf', 'X 2019 pdf')
   - Restrict to mirror sites: `site:archive.org`, `site:github.com`, `site:huggingface.co`, `site:gitlab.com`, `site:gutenberg.org`
   - Try the ISBN if you can infer it
   - Try foreign-language editions or alternate titles
   NEVER re-issue a query you've already tried in this conversation. Look back at your own previous search() calls before picking the next query.
7. The system maintains a verify cache for the duration of this conversation: if you call verify() on a URL that's already been verified, you get the cached result instantly (no browser, no cost) — but you've wasted a turn. Skip URLs that previous verifies already returned ok=false for.
8. Every verify() response includes `partialQuality` (0-10): 0 = wrong content / CAPTCHA, 1-9 = real but incomplete copy of the right book (higher = more complete), 10 = full book. The system automatically falls back to the highest-quality partial if you never find a full book — so a partialQuality>=5 result is a usable fallback. Keep looking for the full book, but you don't need to keep searching indefinitely if you already have a strong partial.

# Be concise
Don't narrate every decision. The user sees subagent events live."""

_CANDIDATES_RE = re.compile(r"<candidates>\s*(\[.*?\])\s*</candidates>", re.DOTALL)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


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


def _find_cached_for_url(
    cache: dict[str, dict[str, Any]], target_url: str
) -> dict[str, Any] | None:
    """Look up a cached verify result matching target_url against any of the
    cached entry's input URL, resolvedUrl, or partialUrl. The model emits
    resolved URLs in <candidates>; verify_cache is keyed by the verify input
    URL, so direct dict lookup misses."""
    if not target_url:
        return None
    for cached in cache.values():
        for key in ("url", "resolvedUrl", "partialUrl"):
            if cached.get(key) == target_url:
                return cached
    return None


def _parse_candidates(text: str) -> list[dict[str, str]]:
    m = _CANDIDATES_RE.search(text)
    if not m:
        return []
    try:
        raw = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        author = str(entry.get("author") or "").strip()
        source_url = str(entry.get("sourceUrl") or "").strip()
        snippet = str(entry.get("snippet") or "").strip()
        if not title or not _URL_RE.match(source_url):
            continue
        out.append(
            {"title": title, "author": author, "sourceUrl": source_url, "snippet": snippet}
        )
    return out


def _search_declaration() -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name="search",
        description=(
            "Run a Google web search. Returns a list of {title, url, snippet}. "
            "Use queries like '<book title> <author> free pdf' or 'books about <topic>'."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(type=types.Type.STRING),
            },
            required=["query"],
        ),
    )


def _verify_declaration() -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name="verify",
        description=(
            "Load a single URL in a real browser, follow any 'Download PDF' buttons, "
            "and confirm it actually serves the expected book as a PDF. "
            "Returns {ok, resolvedUrl, reason}. Use the resolvedUrl in your final candidates."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "url": types.Schema(type=types.Type.STRING),
                "expected_title": types.Schema(type=types.Type.STRING),
            },
            required=["url", "expected_title"],
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
                    _search_declaration(),
                    _verify_declaration(),
                ]
            ),
        ],
    )

    final_text = ""
    start = time.monotonic()
    verify_cache: dict[str, dict[str, Any]] = {}
    best_partial: dict[str, Any] | None = None
    best_partial_expected: str = ""

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
            break
        model_ms = (time.monotonic() - model_t0) * 1000

        text = "".join(text_parts).strip()
        if text:
            final_text = text

        if model_parts:
            contents.append(types.Content(role="model", parts=model_parts))

        logger.info(
            "[orchestrator sid=%s] step=%d model_ms=%.0f text_chars=%d calls=%d names=%s",
            sid, step, model_ms, len(text), len(function_calls),
            [fc.name for fc in function_calls],
        )

        if not function_calls:
            logger.info(
                "[orchestrator sid=%s] STOP reason=agent_done step=%d elapsed=%.1fs",
                sid, step, time.monotonic() - start,
            )
            break

        function_responses: list[types.FunctionResponse] = []

        non_verify_calls = [fc for fc in function_calls if fc.name != "verify"]
        verify_calls = [fc for fc in function_calls if fc.name == "verify"]

        for fc in non_verify_calls:
            args = fc.args or {}
            name = fc.name
            if name == "search":
                q = str(args.get("query") or "")
                yield {
                    "event": "subagent_call",
                    "body": {"agent": "search", "input": {"query": q}},
                }
                t0 = time.monotonic()
                try:
                    results = await search_subagent.search(q)
                except Exception as e:
                    logger.exception(
                        "[orchestrator sid=%s] search subagent failed query=%r", sid, q
                    )
                    function_responses.append(
                        types.FunctionResponse(
                            id=fc.id,
                            name="search",
                            response={"error": str(e), "results": []},
                        )
                    )
                    continue
                logger.info(
                    "[orchestrator sid=%s] search done query=%r count=%d ms=%.0f",
                    sid, q, len(results), (time.monotonic() - t0) * 1000,
                )
                yield {
                    "event": "search_result",
                    "body": {
                        "query": q,
                        "count": len(results),
                        "urls": [{"title": r["title"], "url": r["url"]} for r in results],
                    },
                }
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name="search",
                        response={"results": results},
                    )
                )
            elif name == "research":
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

        if verify_calls:
            events_q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
            final_results: dict[int, dict[str, Any]] = {}
            t0 = time.monotonic()

            async def _run_verify(idx: int, fc: types.FunctionCall) -> None:
                args = fc.args or {}
                url = str(args.get("url") or "")
                expected = str(args.get("expected_title") or "")
                cached = verify_cache.get(url)
                if cached is not None:
                    logger.info(
                        "[orchestrator sid=%s] verify cache hit url=%s ok=%s",
                        sid, url, cached.get("ok"),
                    )
                    final_results[idx] = {**cached, "cached": True}
                    return
                result: dict[str, Any] = {
                    "url": url, "ok": False, "resolvedUrl": None,
                    "reason": "subagent did not return a result",
                }
                try:
                    async for ev in verification_subagent.verify(url, expected, uid):
                        if ev.get("event") == "verify_result":
                            result = ev["body"]
                        else:
                            await events_q.put(ev)
                except asyncio.CancelledError:
                    result = {**result, "reason": "cancelled (peer succeeded)"}
                    final_results[idx] = result
                    raise
                except Exception as e:
                    logger.exception(
                        "[orchestrator sid=%s] verify subagent error idx=%d url=%s",
                        sid, idx, url,
                    )
                    result = {
                        "url": url, "ok": False, "resolvedUrl": None,
                        "reason": f"subagent error: {e}",
                    }
                finally:
                    if idx not in final_results:
                        final_results[idx] = result

            for i, fc in enumerate(verify_calls):
                args = fc.args or {}
                yield {
                    "event": "subagent_call",
                    "body": {
                        "agent": "verify",
                        "input": {
                            "url": args.get("url", ""),
                            "expected_title": args.get("expected_title", ""),
                        },
                    },
                }

            tasks: dict[asyncio.Task[None], int] = {
                asyncio.create_task(_run_verify(i, fc)): i
                for i, fc in enumerate(verify_calls)
            }
            logger.info(
                "[orchestrator sid=%s] step=%d launched %d verify(s) in parallel",
                sid, step, len(tasks),
            )

            winner: tuple[int, dict[str, Any]] | None = None
            pending = set(tasks.keys())

            while pending and winner is None:
                while not events_q.empty():
                    yield events_q.get_nowait()
                done, _ = await asyncio.wait(
                    pending, timeout=0.1, return_when=asyncio.FIRST_COMPLETED
                )
                for t in done:
                    pending.discard(t)
                    i = tasks[t]
                    try:
                        await t
                    except Exception:
                        pass
                    r = final_results.get(i, {"ok": False})
                    cache_url = r.get("url")
                    if cache_url and not r.get("cached"):
                        verify_cache[cache_url] = r
                    pq = int(r.get("partialQuality") or 0)
                    if (
                        not r.get("ok")
                        and pq > 0
                        and r.get("partialUrl")
                        and (best_partial is None or pq > int(best_partial.get("partialQuality") or 0))
                    ):
                        best_partial = r
                        best_partial_expected = str(
                            (verify_calls[i].args or {}).get("expected_title") or ""
                        )
                        logger.info(
                            "[orchestrator sid=%s] new best_partial quality=%d url=%s pages=%d",
                            sid, pq, r.get("partialUrl"), int(r.get("pageCount") or 0),
                        )
                    yield {"event": "verify_result", "body": r}
                    if r.get("ok") and r.get("resolvedUrl"):
                        winner = (i, r)
                        break

            if winner is not None:
                for t in pending:
                    t.cancel()
                for t in pending:
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
                while not events_q.empty():
                    yield events_q.get_nowait()

                win_i, win_r = winner
                fc = verify_calls[win_i]
                expected = str((fc.args or {}).get("expected_title") or "") or query.strip()
                candidate = {
                    "title": expected,
                    "author": "",
                    "sourceUrl": win_r["resolvedUrl"],
                    "snippet": win_r.get("reason", ""),
                    "taskId": win_r.get("taskId"),
                    "sourceKey": win_r.get("sourceKey"),
                    "filename": win_r.get("filename"),
                }
                logger.info(
                    "[orchestrator sid=%s] STOP reason=first_full_success step=%d "
                    "winner_idx=%d cancelled=%d total_ms=%.0f elapsed=%.1fs",
                    sid, step, win_i,
                    len(verify_calls) - len([j for j in final_results if j != win_i and final_results[j].get("ok") is False]) - 1,
                    (time.monotonic() - t0) * 1000, time.monotonic() - start,
                )
                yield {"event": "candidates", "body": [candidate]}
                return

            logger.info(
                "[orchestrator sid=%s] step=%d all %d verify(s) failed total_ms=%.0f",
                sid, step, len(verify_calls), (time.monotonic() - t0) * 1000,
            )
            for i, fc in enumerate(verify_calls):
                function_responses.append(
                    types.FunctionResponse(
                        id=fc.id,
                        name="verify",
                        response=final_results.get(
                            i, {"ok": False, "resolvedUrl": None, "reason": "no result"}
                        ),
                    )
                )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(function_response=fr) for fr in function_responses],
            )
        )
    else:
        logger.info(
            "[orchestrator sid=%s] STOP reason=step_budget steps=%d elapsed=%.1fs",
            sid, _MAX_ORCHESTRATOR_STEPS, time.monotonic() - start,
        )

    candidates = _parse_candidates(final_text)
    for c in candidates:
        cached = _find_cached_for_url(verify_cache, c["sourceUrl"])
        if not cached:
            continue
        if cached.get("taskId") and not c.get("taskId"):
            c["taskId"] = cached["taskId"]
        if cached.get("sourceKey") and not c.get("sourceKey"):
            c["sourceKey"] = cached["sourceKey"]
        if cached.get("filename") and not c.get("filename"):
            c["filename"] = cached["filename"]
    if not candidates and best_partial is not None and best_partial.get("partialUrl"):
        pq = int(best_partial.get("partialQuality") or 0)
        pages = int(best_partial.get("pageCount") or 0)
        reason = str(best_partial.get("reason") or "")
        candidates = [{
            "title": best_partial_expected or query.strip(),
            "author": "",
            "sourceUrl": str(best_partial["partialUrl"]),
            "snippet": (
                f"Preview only ({pages} pages, quality {pq}/10) — full book not "
                f"found. {reason}"
            ),
            "taskId": best_partial.get("taskId"),  # type: ignore[dict-item]
            "sourceKey": best_partial.get("sourceKey"),  # type: ignore[dict-item]
            "filename": best_partial.get("filename"),  # type: ignore[dict-item]
        }]
        logger.info(
            "[orchestrator sid=%s] fallback to best_partial quality=%d pages=%d url=%s",
            sid, pq, pages, best_partial["partialUrl"],
        )
    logger.info(
        "[orchestrator sid=%s] DONE candidates=%d urls=%s",
        sid, len(candidates), [c["sourceUrl"] for c in candidates],
    )
    yield {"event": "candidates", "body": candidates}
