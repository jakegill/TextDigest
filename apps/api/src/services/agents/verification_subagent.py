"""Verification subagent: Computer Use loop scoped to verifying a single URL.

Mirrors the reference Computer Use loop
(https://github.com/google-gemini/computer-use-preview/blob/main/agent.py)
but with a narrow goal: "Visit this URL, confirm it serves the expected PDF."
"""

import asyncio
import io
import logging
import random
import re
import time
import uuid
from typing import Any, AsyncIterator

import pydantic
import pypdfium2 as pdfium
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from urllib.parse import unquote, urlparse

from ...dependencies import PROJECT_ID
from ..titles import flows
from .constants import GEMINI_2_5_COMPUTER_USE_PREVIEW, GEMINI_2_5_FLASH
from .playwright_computer import EnvState, PlaywrightComputer

logger = logging.getLogger("uvicorn.error")

VERTEX_LOCATION = "global"
_FLASH_LOCATION = "us-central1"
_SCREEN_W, _SCREEN_H = 1280, 800
_MAX_STEPS = 12
_MAX_SECONDS = 60
_MAX_RECENT_TURN_WITH_SCREENSHOTS = 3
_DOWNLOAD_TRIGGERING_ACTIONS = {
    "click_at", "type_text_at", "navigate", "key_combination", "drag_and_drop"
}
_DOWNLOAD_POLL_INTERVAL_S = 0.5
_DOWNLOAD_POLL_ATTEMPTS = 6
_DOWNLOAD_SAVE_TIMEOUT_S = 30.0

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)
_flash_client = genai.Client(vertexai=True, project=PROJECT_ID, location=_FLASH_LOCATION)

_PREDEFINED_COMPUTER_USE_FUNCTIONS = {
    "open_web_browser",
    "click_at",
    "hover_at",
    "type_text_at",
    "scroll_document",
    "scroll_at",
    "wait_5_seconds",
    "go_back",
    "go_forward",
    "search",
    "navigate",
    "key_combination",
    "drag_and_drop",
}

_VERIFY_RESULT_RE = re.compile(
    r"<verify_result>\s*(\{.*?\})\s*</verify_result>", re.DOTALL
)

_PDF_RENDER_TARGET_WIDTH = 1024


def _render_page(page: Any) -> bytes:
    w, _ = page.get_size()
    scale = _PDF_RENDER_TARGET_WIDTH / max(w, 1)
    pil = page.render(scale=scale).to_pil()
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def _inspect_pdf(pdf_bytes: bytes) -> tuple[int, bytes, bytes | None] | None:
    """Returns (page_count, first_page_png, last_page_png) or None on failure.
    last_page_png is None when the PDF has only one page."""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        n = len(pdf)
        if n == 0:
            return None
        first_png = _render_page(pdf[0])
        last_png = _render_page(pdf[n - 1]) if n > 1 else None
        return n, first_png, last_png
    except Exception as e:
        logger.info("[verify_subagent] pdf inspect failed error=%s", e.__class__.__name__)
        return None


class _JudgeVerdict(pydantic.BaseModel):
    ok: bool
    reason: str
    partial_quality: int


_JUDGE_PROMPT = (
    "You judge whether a captured PDF is the FULL version of the expected book "
    "AND assign a partial-quality score for use as a fallback.\n\n"
    "Expected book: {expected_title}\n"
    "PDF page count: {page_count}\n\n"
    "Image 1 is the rendered FIRST page of the PDF.\n"
    "{last_page_line}\n\n"
    "Rules for `ok`:\n"
    "- IGNORE the URL and filename entirely. Judge ONLY from the page images "
    "and page count.\n"
    "- First page must look like a real book artifact (cover, title page, "
    "copyright, TOC, or chapter 1 opener). If it's a CAPTCHA, login wall, "
    "error page, ad, or unrelated content → ok=false.\n"
    "- Last page must look like an obvious ENDING (back cover, index, "
    "references, bibliography, appendix, About the Author, or close of a "
    "final chapter). If it stops mid-paragraph, shows 'End of preview / Buy "
    "now / Continue reading on…', or is a stub → ok=false (it's a snippet).\n"
    "- Page count is context only. No hard threshold — some books are short. "
    "Combine with what you see on the pages.\n\n"
    "Rules for `partial_quality` (integer 0-10):\n"
    "- 0 = NOT the expected book at all (CAPTCHA, login wall, error page, "
    "ad, single-page landing, completely unrelated content, wrong book).\n"
    "- 10 = full version of the expected book (must match ok=true).\n"
    "- 1-9 = a real PDF of the expected book but partial. Score higher when "
    "more of the book is present: a single 'free chapter' = 1-2; a few "
    "chapters / MEAP early version with most chapters = 5-7; near-complete "
    "manuscript missing only an appendix = 8-9.\n"
    "- ok=true implies partial_quality=10. ok=false with partial_quality=0 "
    "means it's not the book at all. ok=false with partial_quality>=1 means "
    "it's a real but incomplete copy of the right book.\n\n"
    "The reason field MUST be consistent with ok — if you set ok=true the "
    "reason must affirm (e.g. 'real cover, last page is index, 200 pages'); "
    "if you set ok=false the reason must describe the disqualifying signal "
    "(e.g. 'first page is a CAPTCHA wall', 'last page stops mid-chapter', "
    "'3-page landing PDF, not a book')."
)


async def _judge_capture(
    captured_url: str,
    page_count: int,
    first_png: bytes,
    last_png: bytes | None,
    expected_title: str,
) -> tuple[bool, str, int]:
    last_line = (
        "Image 2 is the rendered LAST page of the PDF."
        if last_png
        else "There is no second image (single-page document)."
    )
    parts: list[Any] = [
        _JUDGE_PROMPT.format(
            expected_title=expected_title,
            page_count=page_count,
            last_page_line=last_line,
        ),
        types.Part.from_bytes(data=first_png, mime_type="image/png"),
    ]
    if last_png:
        parts.append(types.Part.from_bytes(data=last_png, mime_type="image/png"))
    try:
        response = await _flash_client.aio.models.generate_content(
            model=GEMINI_2_5_FLASH,
            contents=parts,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_JudgeVerdict,
            ),
        )
        verdict = _JudgeVerdict.model_validate_json(response.text or "")
        quality = max(0, min(10, int(verdict.partial_quality)))
        logger.info(
            "[verify_subagent] judge_capture url=%s ok=%s partial_quality=%d reason=%r",
            captured_url, verdict.ok, quality, verdict.reason,
        )
        return verdict.ok, verdict.reason, quality
    except Exception as e:
        logger.exception("[verify_subagent] judge_capture failed url=%s", captured_url)
        return False, f"judge error: {e.__class__.__name__}", 0


def _pick_resolved_url(downloads: list[str], fallback: str) -> str:
    for u in reversed(downloads):
        if not u.startswith("blob:"):
            return u
    return fallback


def _filename_from_url(url: str) -> str:
    try:
        path = urlparse(url).path
        last = unquote(path.rsplit("/", 1)[-1]) if "/" in path else unquote(path)
        if last.lower().endswith(".pdf"):
            return last
    except Exception:
        pass
    return "agent-capture.pdf"


_RETRY_BACKOFFS_S = (1.0, 2.0)


async def _generate_with_retry(
    model: str, contents: list[types.Content], config: types.GenerateContentConfig
) -> types.GenerateContentResponse:
    """Call generate_content with retries on empty candidates / 429.
    Up to 3 attempts total (initial + 2 retries) with ~1s, ~2s backoff."""
    last_response: types.GenerateContentResponse | None = None
    for attempt in range(len(_RETRY_BACKOFFS_S) + 1):
        try:
            response = await _client.aio.models.generate_content(
                model=model, contents=contents, config=config,  # type: ignore[arg-type]
            )
        except genai_errors.ClientError as e:
            if attempt < len(_RETRY_BACKOFFS_S) and getattr(e, "status_code", None) == 429:
                backoff = _RETRY_BACKOFFS_S[attempt]
                logger.info(
                    "[verify_subagent] 429 attempt=%d backoff=%.1fs", attempt + 1, backoff,
                )
                await asyncio.sleep(backoff + random.random() * 0.4)
                continue
            raise
        last_response = response
        if response.candidates:
            return response
        if attempt < len(_RETRY_BACKOFFS_S):
            backoff = _RETRY_BACKOFFS_S[attempt]
            logger.info(
                "[verify_subagent] empty candidates attempt=%d backoff=%.1fs",
                attempt + 1, backoff,
            )
            await asyncio.sleep(backoff + random.random() * 0.4)
    assert last_response is not None
    return last_response


def _system_prompt(url: str, expected_title: str) -> str:
    return (
        "# Persona\n"
        "You drive a browser to trigger a PDF download. Your only job is "
        "navigation — the server judges whether the captured PDF is the real "
        "book from rendered first/last pages. You do NOT need to judge.\n\n"
        f"# Target URL\n{url}\n\n"
        f"# Expected book title\n{expected_title}\n\n"
        "# Workflow\n"
        f"1. Navigate to {url}.\n"
        "2. If the response includes `download_captured`, your job is DONE. "
        "Stop immediately — do not click again, do not retry, do not emit "
        "any text. The server takes over from here.\n"
        "3. If no download fires and you land on a landing page: look for a "
        "'Download PDF' / 'PDF' / 'Full text' button or an embedded viewer. "
        "Click it ONCE.\n"
        "4. If the visible page shows a paywall, login wall, 404, or CAPTCHA "
        "and no download was captured, emit:\n"
        "   <verify_result>{\"ok\": false, \"resolvedUrl\": null, \"reason\": \"<short>\"}</verify_result>\n"
        "5. If you genuinely cannot trigger a download after a few tries, "
        "emit the same ok=false block.\n\n"
        "# Downloads are INVISIBLE in the browser screenshot\n"
        "Direct .pdf URLs commonly fire a browser 'download' event and leave "
        "the page blank or showing an error — that is NORMAL. The file was "
        "captured off-screen. The response payload carries `download_captured` "
        "as proof. Trust it. Do NOT retry or conclude failure from a blank "
        "screenshot when `download_captured` is present — just stop.\n\n"
        "# Be concise\n"
        "No filler narration. The user sees the browser actions live."
    )


def _denormalize_x(x: int) -> int:
    return int(x / 1000 * _SCREEN_W)


def _denormalize_y(y: int) -> int:
    return int(y / 1000 * _SCREEN_H)


async def _execute_action(
    computer: PlaywrightComputer, action: types.FunctionCall
) -> EnvState | None:
    name = action.name
    args = action.args or {}
    if name == "open_web_browser":
        return await computer.open_web_browser()
    if name == "click_at":
        return await computer.click_at(_denormalize_x(args["x"]), _denormalize_y(args["y"]))
    if name == "hover_at":
        return await computer.hover_at(_denormalize_x(args["x"]), _denormalize_y(args["y"]))
    if name == "type_text_at":
        return await computer.type_text_at(
            x=_denormalize_x(args["x"]),
            y=_denormalize_y(args["y"]),
            text=args["text"],
            press_enter=args.get("press_enter", False),
            clear_before_typing=args.get("clear_before_typing", True),
        )
    if name == "scroll_document":
        return await computer.scroll_document(args["direction"])
    if name == "scroll_at":
        magnitude = args.get("magnitude", 800)
        direction = args["direction"]
        if direction in ("up", "down"):
            magnitude = _denormalize_y(magnitude)
        else:
            magnitude = _denormalize_x(magnitude)
        return await computer.scroll_at(
            x=_denormalize_x(args["x"]),
            y=_denormalize_y(args["y"]),
            direction=direction,
            magnitude=magnitude,
        )
    if name == "wait_5_seconds":
        return await computer.wait_5_seconds()
    if name == "go_back":
        return await computer.go_back()
    if name == "go_forward":
        return await computer.go_forward()
    if name == "search":
        return await computer.search()
    if name == "navigate":
        return await computer.navigate(args["url"])
    if name == "key_combination":
        return await computer.key_combination(args["keys"].split("+"))
    if name == "drag_and_drop":
        return await computer.drag_and_drop(
            x=_denormalize_x(args["x"]),
            y=_denormalize_y(args["y"]),
            destination_x=_denormalize_x(args["destination_x"]),
            destination_y=_denormalize_y(args["destination_y"]),
        )
    logger.warning("[verify_subagent] unsupported action name=%s", name)
    return None


def _trim_old_screenshots(contents: list[types.Content]) -> None:
    found = 0
    for content in reversed(contents):
        if content.role != "user" or not content.parts:
            continue
        has_screenshot = any(
            p.function_response
            and p.function_response.parts
            and p.function_response.name in _PREDEFINED_COMPUTER_USE_FUNCTIONS
            for p in content.parts
        )
        if not has_screenshot:
            continue
        found += 1
        if found > _MAX_RECENT_TURN_WITH_SCREENSHOTS:
            for p in content.parts:
                if (
                    p.function_response
                    and p.function_response.parts
                    and p.function_response.name in _PREDEFINED_COMPUTER_USE_FUNCTIONS
                ):
                    p.function_response.parts = None


def _action_summary(action: types.FunctionCall) -> dict[str, Any]:
    args = dict(action.args or {})
    if "text" in args and isinstance(args["text"], str) and len(args["text"]) > 80:
        args["text"] = args["text"][:80] + "…"
    return {"action": action.name, "args": args}


def _action_log_str(action: types.FunctionCall) -> str:
    name = action.name or "?"
    args = action.args or {}
    if name == "navigate":
        return f"navigate url={args.get('url')!r}"
    if name == "type_text_at":
        text = args.get("text") or ""
        if len(text) > 60:
            text = text[:60] + "…"
        return f"type_text_at x={args.get('x')} y={args.get('y')} text={text!r}"
    if name in ("click_at", "hover_at"):
        return f"{name} x={args.get('x')} y={args.get('y')}"
    return name


def _parse_verify_result(text: str) -> dict[str, Any] | None:
    m = _VERIFY_RESULT_RE.search(text)
    if not m:
        return None
    try:
        import json
        return json.loads(m.group(1))
    except Exception:
        return None


_DENIAL_MARKERS = (
    "unable",
    "couldn't access",
    "could not access",
    "cannot access",
    "couldn't load",
    "could not load",
    "cannot load",
    "captcha",
    "blocked",
    "failed",
    "denied",
    "forbidden",
    "no access",
    "not accessible",
    "preview only",
    "sample only",
)


def _reason_indicates_failure(reason: str) -> bool:
    if not reason:
        return False
    r = reason.lower()
    return any(m in r for m in _DENIAL_MARKERS)


async def verify(
    url: str, expected_title: str, uid: str
) -> AsyncIterator[dict[str, Any]]:
    """Yields browser_action events as the subagent works, finally yields one
    verify_result event with {url, ok, resolvedUrl, reason, partialQuality,
    partialUrl, pageCount, taskId, sourceKey, filename}."""
    vid = uuid.uuid4().hex[:6]
    logger.info(
        "[verify_subagent vid=%s] START url=%s expected_title=%r budgets steps<=%d secs<=%d",
        vid, url, expected_title, _MAX_STEPS, _MAX_SECONDS,
    )

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=f"Verify URL: {url}")])
    ]
    config = types.GenerateContentConfig(
        system_instruction=_system_prompt(url, expected_title),
        temperature=1,
        top_p=0.95,
        max_output_tokens=4096,
        tools=[
            types.Tool(
                computer_use=types.ComputerUse(
                    environment=types.Environment.ENVIRONMENT_BROWSER,
                ),
            ),
        ],
    )

    final_text = ""
    captured_inspection: tuple[str, int, bytes, bytes | None] | None = None
    computer: PlaywrightComputer | None = None
    try:
        computer = PlaywrightComputer(screen_size=(_SCREEN_W, _SCREEN_H))
        await computer.__aenter__()
        start = time.monotonic()

        for step in range(1, _MAX_STEPS + 1):
            if time.monotonic() - start > _MAX_SECONDS:
                logger.info(
                    "[verify_subagent vid=%s] STOP reason=time_budget step=%d", vid, step
                )
                break

            model_t0 = time.monotonic()
            try:
                response = await _generate_with_retry(
                    model=GEMINI_2_5_COMPUTER_USE_PREVIEW,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                logger.exception(
                    "[verify_subagent vid=%s] generate_content failed step=%d", vid, step
                )
                yield {
                    "event": "verify_result",
                    "body": {
                        "url": url, "ok": False, "resolvedUrl": None,
                        "reason": f"model error: {e}",
                    },
                }
                return
            model_ms = (time.monotonic() - model_t0) * 1000

            if not response.candidates:
                logger.warning("[verify_subagent vid=%s] no candidates step=%d", vid, step)
                break

            candidate = response.candidates[0]
            if candidate.content:
                contents.append(candidate.content)

            text_parts: list[str] = []
            function_calls: list[types.FunctionCall] = []
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if part.text:
                        text_parts.append(part.text)
                    if part.function_call:
                        function_calls.append(part.function_call)
            text = "".join(text_parts).strip()
            if text:
                final_text = text

            logger.info(
                "[verify_subagent vid=%s] step=%d model_ms=%.0f text_chars=%d actions=%d names=%s",
                vid, step, model_ms, len(text), len(function_calls),
                [fc.name for fc in function_calls],
            )

            if not function_calls:
                logger.info(
                    "[verify_subagent vid=%s] STOP reason=agent_done step=%d", vid, step
                )
                break

            function_responses: list[types.FunctionResponse] = []
            for fc in function_calls:
                logger.info(
                    "[verify_subagent vid=%s] step=%d %s",
                    vid, step, _action_log_str(fc),
                )
                yield {"event": "browser_action", "body": _action_summary(fc)}
                downloads_before = set(computer.collected_download_urls())
                try:
                    env_state = await _execute_action(computer, fc)
                except Exception as e:
                    logger.exception(
                        "[verify_subagent vid=%s] action failed name=%s", vid, fc.name
                    )
                    function_responses.append(
                        types.FunctionResponse(
                            name=fc.name or "unknown",
                            response={"error": str(e)},
                        )
                    )
                    continue
                if env_state is None:
                    function_responses.append(
                        types.FunctionResponse(
                            name=fc.name or "unknown",
                            response={"error": "unsupported action"},
                        )
                    )
                    continue
                if fc.name in _DOWNLOAD_TRIGGERING_ACTIONS:
                    for _ in range(_DOWNLOAD_POLL_ATTEMPTS):
                        if any(
                            u not in downloads_before
                            for u in computer.collected_download_urls()
                        ):
                            break
                        await asyncio.sleep(_DOWNLOAD_POLL_INTERVAL_S)
                    await computer.wait_for_pending_downloads(
                        timeout=_DOWNLOAD_SAVE_TIMEOUT_S
                    )
                new_downloads = [
                    u for u in computer.collected_download_urls() if u not in downloads_before
                ]
                response_payload: dict[str, Any] = {"url": env_state.url}
                response_parts: list[types.FunctionResponsePart] = [
                    types.FunctionResponsePart(
                        inline_data=types.FunctionResponseBlob(
                            mime_type="image/png", data=env_state.screenshot
                        )
                    )
                ]
                if new_downloads:
                    captured = new_downloads[-1]
                    response_payload["download_captured"] = captured
                    pdf_bytes = computer.get_download_bytes(captured)
                    inspection = _inspect_pdf(pdf_bytes) if pdf_bytes else None
                    if inspection:
                        page_count, first_png, last_png = inspection
                        captured_inspection = (captured, page_count, first_png, last_png)
                        response_payload["page_count"] = page_count
                        response_payload["note"] = (
                            f"A PDF was captured ({len(pdf_bytes or b'')} bytes, "
                            f"page_count={page_count}). The server will now judge it "
                            "from the rendered first/last pages — your browser-driving "
                            "job is done."
                        )
                        logger.info(
                            "[verify_subagent vid=%s] step=%d inspected captured pdf url=%s pdf_bytes=%d pages=%d first_png=%d last_png=%d",
                            vid, step, captured, len(pdf_bytes or b''), page_count,
                            len(first_png), len(last_png or b''),
                        )
                    else:
                        response_payload["note"] = (
                            f"A download was captured from {captured} but it could not "
                            "be rendered as a PDF (corrupt, encrypted, or not actually a "
                            "PDF). Treat this as a failed verification — do NOT emit "
                            "ok=true based on the URL alone."
                        )
                        logger.info(
                            "[verify_subagent vid=%s] step=%d capture not renderable url=%s pdf_bytes=%d",
                            vid, step, captured, len(pdf_bytes or b''),
                        )
                function_responses.append(
                    types.FunctionResponse(
                        name=fc.name or "unknown",
                        response=response_payload,
                        parts=response_parts,
                    )
                )

            if captured_inspection is not None:
                logger.info(
                    "[verify_subagent vid=%s] STOP reason=download_captured step=%d",
                    vid, step,
                )
                break

            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(function_response=fr) for fr in function_responses],
                )
            )
            _trim_old_screenshots(contents)
        else:
            logger.info(
                "[verify_subagent vid=%s] STOP reason=step_budget steps=%d", vid, _MAX_STEPS
            )

        downloads = computer.collected_download_urls() if computer else []
        partial_quality = 0
        page_count_out = 0
        partial_url: str | None = None
        task_id_out: str | None = None
        source_key_out: str | None = None
        filename_out: str | None = None

        if captured_inspection is not None:
            captured_url, page_count, first_png, last_png = captured_inspection
            page_count_out = page_count
            ok, reason, partial_quality = await _judge_capture(
                captured_url, page_count, first_png, last_png, expected_title,
            )
            non_blob = _pick_resolved_url(downloads, url)
            resolved = non_blob if ok else None
            if partial_quality > 0:
                partial_url = non_blob
            if ok:
                partial_quality = 10
            if partial_quality >= 1 and computer is not None:
                pdf_bytes = computer.get_download_bytes(captured_url) or b""
                if pdf_bytes:
                    filename_out = _filename_from_url(captured_url)
                    try:
                        task_id_out, source_key_out = await flows.stage_agent_capture(
                            uid, pdf_bytes, filename_out,
                        )
                        logger.info(
                            "[verify_subagent vid=%s] staged taskId=%s sourceKey=%s bytes=%d",
                            vid, task_id_out, source_key_out, len(pdf_bytes),
                        )
                    except Exception:
                        logger.exception(
                            "[verify_subagent vid=%s] stage_agent_capture failed", vid
                        )
                        task_id_out = None
                        source_key_out = None
                        filename_out = None
        else:
            parsed_raw = _parse_verify_result(final_text)
            parsed = parsed_raw or {}
            ok = bool(parsed.get("ok"))
            resolved = parsed.get("resolvedUrl")
            reason = parsed.get("reason") or ("no verdict emitted" if not parsed else "")

            reason_denies = _reason_indicates_failure(reason)
            if ok and reason_denies:
                logger.info(
                    "[verify_subagent vid=%s] forced ok=false: reason contradicts (%r)",
                    vid, reason,
                )
                ok = False

            if parsed_raw is None and downloads and not reason_denies:
                resolved = _pick_resolved_url(downloads, url)
                ok = True
                reason = reason or "captured via browser download event"
            if ok:
                partial_quality = 10

        result = {
            "url": url,
            "ok": ok,
            "resolvedUrl": resolved,
            "reason": reason,
            "partialQuality": partial_quality,
            "partialUrl": partial_url,
            "pageCount": page_count_out,
            "taskId": task_id_out,
            "sourceKey": source_key_out,
            "filename": filename_out,
        }
        logger.info(
            "[verify_subagent vid=%s] DONE ok=%s resolved=%s partial=%d pages=%d taskId=%s reason=%r downloads=%d",
            vid, ok, resolved, partial_quality, page_count_out, task_id_out, reason, len(downloads),
        )
        yield {"event": "verify_result", "body": result}
    finally:
        if computer is not None:
            await computer.__aexit__(None, None, None)
            logger.info("[verify_subagent vid=%s] browser closed", vid)
