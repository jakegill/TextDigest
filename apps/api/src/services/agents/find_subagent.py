"""Find subagent: deterministic search→verify→retry pipeline for a specific
named book.

Owns the entire find-flow that used to live in the title_finder orchestrator
prompt and Python loop: build a query ladder, dispatch parallel verifies,
forward inner events, track best_partial fallback, emit candidates. Reuses
search_subagent.search() and verification_subagent.verify() unchanged.

Yields events compatible with the existing find-title SSE stream:
  - subagent_call (agent="search" | "verify")
  - search_result
  - verify_result
  - browser_action (forwarded from verification_subagent)
  - candidates (exactly once at end; list may be empty)
"""

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from . import search_subagent, verification_subagent

logger = logging.getLogger("uvicorn.error")

_PAYWALL_HOSTS = {
    "researchgate.net",
    "scribd.com",
    "academia.edu",
    "libgen",
    "z-lib",
    "dokumen.pub",
    "epdf.pub",
    "download-book.com",
}
_MAX_VERIFY_PER_QUERY = 5


def _build_query_ladder(title: str, author: str) -> list[str]:
    t = title.strip()
    a = author.strip()
    if a:
        return [
            f"{t} {a} free pdf",
            f"{t} {a} full book pdf",
            f"{t} {a} site:archive.org",
            f"{t} {a} site:github.com OR site:gitlab.com OR site:huggingface.co",
            f"{t} {a} pdf 2nd edition",
        ]
    return [
        f"{t} free pdf",
        f"{t} full book pdf",
        f"{t} site:archive.org",
        f"{t} site:github.com OR site:gitlab.com OR site:huggingface.co",
        f"{t} pdf",
    ]


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_paywall(url: str) -> bool:
    host = _hostname(url)
    return any(blocked in host for blocked in _PAYWALL_HOSTS)


def _pick_verify_urls(
    results: list[dict[str, str]],
    seen: set[str],
    limit: int = _MAX_VERIFY_PER_QUERY,
) -> tuple[list[str], dict[str, int]]:
    picked: list[str] = []
    skipped_seen = 0
    skipped_paywall = 0
    skipped_empty = 0
    for r in results:
        url = (r.get("url") or "").strip()
        if not url:
            skipped_empty += 1
            continue
        if url in seen:
            skipped_seen += 1
            continue
        if _is_paywall(url):
            skipped_paywall += 1
            continue
        picked.append(url)
        if len(picked) >= limit:
            break
    stats = {
        "total": len(results),
        "picked": len(picked),
        "skipped_seen": skipped_seen,
        "skipped_paywall": skipped_paywall,
        "skipped_empty": skipped_empty,
    }
    return picked, stats


async def _run_verify(
    fid: str,
    idx: int,
    url: str,
    expected_title: str,
    uid: str,
    verify_cache: dict[str, dict[str, Any]],
    events_q: asyncio.Queue[dict[str, Any]],
    final_results: dict[int, dict[str, Any]],
) -> None:
    cached = verify_cache.get(url)
    if cached is not None:
        logger.info(
            "[find_subagent fid=%s] verify cache hit idx=%d url=%s ok=%s pq=%s",
            fid, idx, url, cached.get("ok"), cached.get("partialQuality"),
        )
        final_results[idx] = {**cached, "cached": True}
        return
    t0 = time.monotonic()
    result: dict[str, Any] = {
        "url": url,
        "ok": False,
        "resolvedUrl": None,
        "reason": "subagent did not return a result",
    }
    try:
        async for ev in verification_subagent.verify(url, expected_title, uid):
            if ev.get("event") == "verify_result":
                result = ev["body"]
            else:
                await events_q.put(ev)
    except asyncio.CancelledError:
        logger.info(
            "[find_subagent fid=%s] verify cancelled idx=%d url=%s after %.1fs",
            fid, idx, url, time.monotonic() - t0,
        )
        result = {**result, "reason": "cancelled (peer succeeded)"}
        final_results[idx] = result
        raise
    except Exception as e:
        logger.exception(
            "[find_subagent fid=%s] verify error idx=%d url=%s", fid, idx, url,
        )
        result = {
            "url": url,
            "ok": False,
            "resolvedUrl": None,
            "reason": f"subagent error: {e}",
        }
    finally:
        if idx not in final_results:
            final_results[idx] = result
        logger.info(
            "[find_subagent fid=%s] verify done idx=%d url=%s ok=%s pq=%s pages=%s ms=%.0f",
            fid, idx, url,
            result.get("ok"), result.get("partialQuality"),
            result.get("pageCount"), (time.monotonic() - t0) * 1000,
        )


async def _parallel_verify(
    fid: str,
    urls: list[str],
    expected_title: str,
    uid: str,
    verify_cache: dict[str, dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Dispatches verifies in parallel, yields subagent_call/browser_action/
    verify_result events as they happen. Final yields control signals:
      - {"event": "_winner", "body": result}
      - {"event": "_partial", "body": result}
      - {"event": "_all_failed", "body": {}}
    The underscore events are internal control signals consumed by stream_find;
    they are NOT forwarded to the SSE wire."""
    events_q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    final_results: dict[int, dict[str, Any]] = {}

    for url in urls:
        yield {
            "event": "subagent_call",
            "body": {
                "agent": "verify",
                "input": {"url": url, "expected_title": expected_title},
            },
        }

    tasks: dict[asyncio.Task[None], int] = {
        asyncio.create_task(
            _run_verify(
                fid, i, url, expected_title, uid, verify_cache, events_q, final_results
            )
        ): i
        for i, url in enumerate(urls)
    }
    pv_t0 = time.monotonic()
    logger.info(
        "[find_subagent fid=%s] parallel_verify launched %d task(s)",
        fid, len(tasks),
    )

    best_partial: dict[str, Any] | None = None
    winner: dict[str, Any] | None = None
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
                and (
                    best_partial is None
                    or pq > int(best_partial.get("partialQuality") or 0)
                )
            ):
                best_partial = r
            yield {"event": "verify_result", "body": r}
            if r.get("ok") and r.get("resolvedUrl"):
                winner = r
                break

    if winner is not None:
        cancelled = len(pending)
        for t in pending:
            t.cancel()
        for t in pending:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        while not events_q.empty():
            yield events_q.get_nowait()
        logger.info(
            "[find_subagent fid=%s] parallel_verify winner url=%s cancelled=%d elapsed=%.1fs",
            fid, winner.get("resolvedUrl"), cancelled, time.monotonic() - pv_t0,
        )
        yield {"event": "_winner", "body": winner}
        return

    while not events_q.empty():
        yield events_q.get_nowait()
    if best_partial is not None:
        logger.info(
            "[find_subagent fid=%s] parallel_verify no winner; best_partial quality=%s elapsed=%.1fs",
            fid, best_partial.get("partialQuality"), time.monotonic() - pv_t0,
        )
        yield {"event": "_partial", "body": best_partial}
    else:
        logger.info(
            "[find_subagent fid=%s] parallel_verify all failed elapsed=%.1fs",
            fid, time.monotonic() - pv_t0,
        )
        yield {"event": "_all_failed", "body": {}}


def _to_winner_candidate(
    r: dict[str, Any], fallback_title: str, fallback_author: str
) -> dict[str, Any]:
    return {
        "title": r.get("title") or fallback_title,
        "author": r.get("author") or fallback_author,
        "sourceUrl": r["resolvedUrl"],
        "snippet": r.get("reason", ""),
        "taskId": r.get("taskId"),
        "sourceKey": r.get("sourceKey"),
        "filename": r.get("filename"),
        "coverUrl": r.get("coverUrl"),
    }


def _to_partial_candidate(
    r: dict[str, Any], fallback_title: str, fallback_author: str
) -> dict[str, Any]:
    pq = int(r.get("partialQuality") or 0)
    pages = int(r.get("pageCount") or 0)
    reason = str(r.get("reason") or "")
    return {
        "title": r.get("title") or fallback_title,
        "author": r.get("author") or fallback_author,
        "sourceUrl": str(r["partialUrl"]),
        "snippet": (
            f"Preview only ({pages} pages, quality {pq}/10) — full book not "
            f"found. {reason}"
        ),
        "taskId": r.get("taskId"),
        "sourceKey": r.get("sourceKey"),
        "filename": r.get("filename"),
        "coverUrl": r.get("coverUrl"),
    }


async def stream_find(
    title: str,
    author: str,
    uid: str,
) -> AsyncIterator[dict[str, Any]]:
    """Driver for the specific-book find pipeline. Yields subagent_call,
    search_result, verify_result, and browser_action events from the inner
    subagents, then exactly one `candidates` event at the end. The candidates
    list may be empty if nothing matched."""
    fid = uuid.uuid4().hex[:8]
    start = time.monotonic()
    queries = _build_query_ladder(title, author)
    logger.info(
        "[find_subagent fid=%s] START title=%r author=%r uid=%s queries=%d",
        fid, title, author, uid, len(queries),
    )

    seen_urls: set[str] = set()
    verify_cache: dict[str, dict[str, Any]] = {}
    best_partial: dict[str, Any] | None = None
    expected_title = title.strip() or "(unknown)"

    for q_idx, query in enumerate(queries):
        logger.info(
            "[find_subagent fid=%s] q_idx=%d/%d START query=%r",
            fid, q_idx + 1, len(queries), query,
        )
        yield {
            "event": "subagent_call",
            "body": {"agent": "search", "input": {"query": query}},
        }
        t0 = time.monotonic()
        try:
            results = await search_subagent.search(query)
        except Exception:
            logger.exception(
                "[find_subagent fid=%s] search failed q_idx=%d query=%r",
                fid, q_idx, query,
            )
            continue
        logger.info(
            "[find_subagent fid=%s] search q_idx=%d query=%r count=%d ms=%.0f",
            fid, q_idx, query, len(results), (time.monotonic() - t0) * 1000,
        )
        yield {
            "event": "search_result",
            "body": {
                "query": query,
                "count": len(results),
                "urls": [{"title": r["title"], "url": r["url"]} for r in results],
            },
        }

        urls, filter_stats = _pick_verify_urls(results, seen_urls)
        logger.info(
            "[find_subagent fid=%s] q_idx=%d filter total=%d picked=%d "
            "skipped_seen=%d skipped_paywall=%d",
            fid, q_idx + 1, filter_stats["total"], filter_stats["picked"],
            filter_stats["skipped_seen"], filter_stats["skipped_paywall"],
        )
        if not urls:
            logger.info(
                "[find_subagent fid=%s] q_idx=%d no fresh non-paywall urls; "
                "advancing to next query",
                fid, q_idx + 1,
            )
            continue
        seen_urls.update(urls)

        winner: dict[str, Any] | None = None
        async for ev in _parallel_verify(fid, urls, expected_title, uid, verify_cache):
            kind = ev.get("event")
            if kind == "_winner":
                winner = ev["body"]
            elif kind == "_partial":
                partial = ev["body"]
                pq = int(partial.get("partialQuality") or 0)
                if (
                    best_partial is None
                    or pq > int(best_partial.get("partialQuality") or 0)
                ):
                    best_partial = partial
                    logger.info(
                        "[find_subagent fid=%s] new best_partial quality=%d url=%s",
                        fid, pq, partial.get("partialUrl"),
                    )
            elif kind == "_all_failed":
                pass
            else:
                yield ev

        if winner is not None:
            cand = _to_winner_candidate(winner, expected_title, author)
            logger.info(
                "[find_subagent fid=%s] DONE reason=winner q_idx=%d elapsed=%.1fs url=%s",
                fid, q_idx, time.monotonic() - start, cand.get("sourceUrl"),
            )
            yield {"event": "candidates", "body": [cand]}
            return

    if best_partial is not None and best_partial.get("partialUrl"):
        cand = _to_partial_candidate(best_partial, expected_title, author)
        if cand.get("coverUrl"):
            logger.info(
                "[find_subagent fid=%s] DONE reason=partial_fallback quality=%s elapsed=%.1fs",
                fid, best_partial.get("partialQuality"), time.monotonic() - start,
            )
            yield {"event": "candidates", "body": [cand]}
            return

    logger.info(
        "[find_subagent fid=%s] DONE reason=no_candidate elapsed=%.1fs",
        fid, time.monotonic() - start,
    )
    yield {"event": "candidates", "body": []}
