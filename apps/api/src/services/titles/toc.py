import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, ValidationError
from rapidfuzz import fuzz, process

from ...dependencies import PROJECT_ID
from ...models.titles import SkeletonEntry, TocEntry
from .constants import GEMINI_2_5_FLASH

VERTEX_LOCATION = "us-central1"
FIRST_PAGES_TO_SHOW = 10
PAGE_CONTENTS_TRUNCATE = 4000
MAX_TOOL_CALLS = 400
ANCHOR_MATCH_THRESHOLD = 60.0

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


class _TocEntryCandidate(BaseModel):
    title: str
    level: int
    pdfPage: int


def _slugify(text: str, seen: Counter) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-") or "section"
    n = seen[s]
    seen[s] += 1
    return s if n == 0 else f"{s}-{n}"


def heading_skeleton(content_list: list[dict]) -> list[SkeletonEntry]:
    seen: Counter = Counter()
    out: list[SkeletonEntry] = []
    for b in content_list:
        if b.get("type") != "title":
            continue
        text = (b.get("text") or "").strip()
        if not text:
            continue
        out.append(
            SkeletonEntry(
                title=text,
                level=int(b.get("text_level") or 1),
                pdfPage=int(b.get("page_idx", 0)) + 1,
                anchor=_slugify(text, seen),
            )
        )
    return out


def _block_to_text(b: dict) -> str:
    t = b.get("type")
    if t in ("text", "title"):
        return (b.get("text") or "").strip()
    if t == "list":
        items = b.get("list_items") or []
        return "\n".join(str(i) for i in items)
    if t == "image":
        cap = b.get("image_caption") or []
        return f"[image: {' '.join(cap)}]" if cap else "[image]"
    return ""


def _index_by_page(content_list: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for b in content_list:
        p = int(b.get("page_idx", 0))
        out.setdefault(p, []).append(b)
    return out


@dataclass
class _AgentState:
    skeleton: list[SkeletonEntry]
    by_page: dict[int, list[dict]] = field(default_factory=dict)
    total_pages: int = 0
    submitted: list[dict] | None = None


def _build_tools(state: _AgentState) -> list:
    def get_page_contents(page_number: int) -> str:
        """Read the text content of a single PDF page.

        Args:
            page_number: 1-based PDF page number (1 = first page of the PDF).

        Returns:
            All text/title/list/image-caption content from that page, joined
            with newlines, truncated to ~4000 chars. Empty string if the page
            has no extracted content or is out of range.
        """
        idx = page_number - 1
        if idx < 0 or idx not in state.by_page:
            return ""
        parts = [_block_to_text(b) for b in state.by_page[idx]]
        joined = "\n".join(p for p in parts if p)
        if len(joined) > PAGE_CONTENTS_TRUNCATE:
            return joined[:PAGE_CONTENTS_TRUNCATE] + "\n[…truncated…]"
        return joined

    def get_page_headings(page_number: int) -> list[dict]:
        """List only the heading blocks on a single PDF page.

        Cheaper than `get_page_contents` when you just need to confirm whether
        a chapter heading lives on a candidate page.

        Args:
            page_number: 1-based PDF page number.

        Returns:
            List of headings on that page, each a dict with keys: title (str),
            level (int 1-4), anchor (str), skeleton_index (int — the index
            into the skeleton, useful for ordering). Empty list if none.
        """
        out: list[dict] = []
        for i, s in enumerate(state.skeleton):
            if s.pdfPage == page_number:
                out.append(
                    {
                        "title": s.title,
                        "level": s.level,
                        "anchor": s.anchor,
                        "skeleton_index": i,
                    }
                )
        return out

    def find_heading(
        query: str = "",
        level_hint: int = 0,
        after_skeleton_index: int = -1,
    ) -> list[dict]:
        """Fuzzy-search the document's heading skeleton.

        Backup tool for when there is no printed TOC or when you want to grab
        an anchor by title without knowing the page. WARNING: the skeleton
        also contains headings detected on TOC pages themselves, so a query
        may match the *TOC entry* (early page) rather than the real chapter
        heading. Prefer `get_page_contents` / `get_page_headings` to verify.

        Args:
            query: Title text to fuzzy-match. Empty string returns nothing.
            level_hint: 1-4 to restrict to that level. 0 means any level.
            after_skeleton_index: only return entries with skeleton_index
                strictly greater. -1 to ignore.

        Returns:
            Up to 5 candidates, each with skeleton_index, title, level,
            pdfPage, anchor, and match_score (0-100).
        """
        if not query.strip():
            return []
        candidates = [
            (i, s)
            for i, s in enumerate(state.skeleton)
            if (level_hint == 0 or s.level == level_hint)
            and (after_skeleton_index < 0 or i > after_skeleton_index)
        ]
        if not candidates:
            return []
        choices = {i: s.title for i, s in candidates}
        matches = process.extract(
            query, choices, scorer=fuzz.WRatio, limit=5, score_cutoff=60.0
        )
        out: list[dict] = []
        for _, score, idx in matches:
            s = state.skeleton[idx]
            out.append(
                {
                    "skeleton_index": idx,
                    "title": s.title,
                    "level": s.level,
                    "pdfPage": s.pdfPage,
                    "anchor": s.anchor,
                    "match_score": int(score),
                }
            )
        return out

    def submit_toc(entries_json: str) -> str:
        """Submit the final Table of Contents and end the agent loop.

        Call this exactly once after you've resolved every entry.

        Args:
            entries_json: A JSON-encoded array. Each object MUST have keys:
                title (str), level (int 1-4), pdfPage (int, 1-based PDF page
                where the section ACTUALLY starts in this PDF, not the printed
                page number). Example:
                [{"title":"Machine Learning","level":1,"pdfPage":11}]

        Returns:
            "ok" on success, or an error message for malformed JSON.
        """
        try:
            parsed = json.loads(entries_json)
        except json.JSONDecodeError as e:
            return f"error: invalid JSON: {e}"
        if not isinstance(parsed, list):
            return "error: expected a JSON array at the top level"
        state.submitted = parsed
        return "ok"

    return [get_page_contents, get_page_headings, find_heading, submit_toc]


def _resolve_anchor(
    title: str, pdf_page: int, skeleton: list[SkeletonEntry], seen: Counter
) -> str:
    on_page = [s for s in skeleton if s.pdfPage == pdf_page]
    if on_page:
        choices = {i: s.title for i, s in enumerate(on_page)}
        match = process.extractOne(
            title, choices, scorer=fuzz.WRatio, score_cutoff=ANCHOR_MATCH_THRESHOLD
        )
        if match:
            _, _, local_idx = match
            return on_page[local_idx].anchor
    return _slugify(title, seen)


def _validate_submitted(
    raw_entries: list[dict], skeleton: list[SkeletonEntry]
) -> list[TocEntry]:
    seen: Counter = Counter()
    out: list[TocEntry] = []
    for raw in raw_entries:
        try:
            cand = _TocEntryCandidate.model_validate(raw)
        except (ValidationError, TypeError) as e:
            logger.warning(f"[toc] dropping invalid entry {raw!r}: {e}")
            continue
        if cand.level < 1 or cand.level > 4 or cand.pdfPage < 1:
            logger.warning(f"[toc] dropping out-of-range entry {raw!r}")
            continue
        anchor = _resolve_anchor(cand.title, cand.pdfPage, skeleton, seen)
        out.append(
            TocEntry(
                title=cand.title,
                level=cand.level,
                pdfPage=cand.pdfPage,
                anchor=anchor,
            )
        )
    return out


def _run_toc_agent(
    prompt: str,
    skeleton: list[SkeletonEntry],
    by_page: dict[int, list[dict]],
    total_pages: int,
) -> list[TocEntry] | None:
    state = _AgentState(
        skeleton=skeleton, by_page=by_page, total_pages=total_pages
    )
    tools = _build_tools(state)
    try:
        _client.models.generate_content(
            model=GEMINI_2_5_FLASH,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=MAX_TOOL_CALLS,
                ),
            ),
        )
    except Exception:
        logger.exception("[toc] agent call failed")

    if state.submitted is None:
        logger.error("[toc] agent never called submit_toc")
        return None

    entries = _validate_submitted(state.submitted, skeleton)
    return entries or None


def _fallback_top_level_toc(skeleton: list[SkeletonEntry]) -> list[TocEntry]:
    return [TocEntry(**s.model_dump()) for s in skeleton if s.level <= 2]


def _format_first_pages(by_page: dict[int, list[dict]], n: int) -> str:
    chunks: list[str] = []
    for p in range(n):
        if p not in by_page:
            continue
        parts = [_block_to_text(b) for b in by_page[p]]
        body = "\n".join(s for s in parts if s)
        if body:
            chunks.append(f"--- PDF page {p + 1} ---\n{body}")
    return "\n\n".join(chunks)


def _format_top_level_hint(skeleton: list[SkeletonEntry]) -> str:
    lines = [
        f"  pdfPage={s.pdfPage}  L{s.level}  {s.title}"
        for s in skeleton
        if s.level <= 2
    ]
    return "\n".join(lines)


def extract_toc(
    uid: str, title_id: str, content_list: list[dict]
) -> tuple[list[TocEntry], str]:
    del uid, title_id
    skeleton = heading_skeleton(content_list)
    if not skeleton:
        return [], "skeleton"

    by_page = _index_by_page(content_list)
    total_pages = (max(by_page.keys()) + 1) if by_page else 0
    first_pages_text = _format_first_pages(by_page, FIRST_PAGES_TO_SHOW)
    skeleton_hint = _format_top_level_hint(skeleton)

    prompt = (
        "You are building a Table of Contents for an e-reader. Output is JSON: "
        "a list of entries with `title`, `level` (1=top, 4=deepest), and "
        "`pdfPage` (the ACTUAL 1-based PDF page number where the section "
        "starts in this PDF).\n\n"
        "STEP 1 — find the printed TOC.\n"
        "Read the text of the first PDF pages below. Look for a printed Table "
        "of Contents (header like 'Contents', 'Table of Contents', "
        "'Sommaire', 'Index'). If found, identify every entry: its title, its "
        "printed page number (the number next to the title), and its indent "
        "level. Note: printed page numbers refer to the book's own numbering, "
        "NOT the PDF page numbers.\n\n"
        "STEP 2 — find the front-matter offset.\n"
        "Pick the FIRST clearly-distinctive chapter entry from the printed TOC. "
        "Its printed page might be 11, but in the PDF it could be on page 13 "
        "(due to cover, foreword, lists of figures, etc.). Use the "
        "`get_page_contents` tool to look at PDF pages around `printed_page` "
        "(try printed_page, printed_page+1, printed_page+2, ...) until you "
        "find the page where that chapter heading actually appears at the top "
        "of the page. The offset = pdf_page − printed_page. Typical offsets "
        "are 0 to +10.\n\n"
        "STEP 3 — verify each entry.\n"
        "Apply the offset to every printed-TOC entry to get a candidate "
        "pdf_page. Use `get_page_headings(pdf_page)` (cheap) to confirm the "
        "chapter heading is on the expected page. If not, try ±1 or ±2 pages. "
        "Some books shift offset mid-way; re-verify a spot-check entry every "
        "few chapters.\n\n"
        "STEP 4 — submit.\n"
        "Call `submit_toc` ONCE with a JSON array of {title, level, pdfPage} "
        "entries in document order. Preserve the printed-TOC title text "
        "verbatim. Drop entries whose pdfPage you cannot confidently locate.\n\n"
        "If there is NO printed TOC in the first pages, fall back: synthesize "
        "from the heading skeleton hint below. Pick meaningful level-1 and "
        "level-2 entries. Use `get_page_headings` to verify each pick (the "
        "skeleton's pdfPages can be wrong on TOC pages, so always verify). "
        "Skip noise like 'Page 1', captions, or stray emphasis.\n\n"
        f"Total PDF pages in this document: {total_pages}\n\n"
        f"=== First {FIRST_PAGES_TO_SHOW} PDF pages ===\n"
        f"{first_pages_text}\n\n"
        "=== Heading skeleton hint (level-1 and level-2 only; pages may be "
        "wrong on TOC pages — always verify with tools) ===\n"
        f"{skeleton_hint}\n"
    )

    entries = _run_toc_agent(prompt, skeleton, by_page, total_pages)
    if entries:
        return entries, "doc"

    logger.warning("[toc] agent failed, returning level-1/2 fallback")
    return _fallback_top_level_toc(skeleton), "skeleton"
