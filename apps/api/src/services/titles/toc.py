import json
import re
import unicodedata
from collections import Counter
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

from ...dependencies import PROJECT_ID
from ...models.titles import DocTocEntry, SkeletonEntry, TocEntry
from . import vector_index
from .constants import GEMINI_2_5_FLASH, GEMINI_3_1_FLASH_LITE

VERTEX_LOCATION = "us-central1"
EARLY_PAGES = 10

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


class _DocTocResult(BaseModel):
    found: bool
    entries: list[DocTocEntry]


class _MatchResult(BaseModel):
    skeleton_indices: list[int | None]


class _PruneResult(BaseModel):
    keep_indices: list[int]


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


def detect_doc_toc(content_list: list[dict]) -> list[DocTocEntry] | None:
    early = "\n".join(
        (b.get("text") or "").strip()
        for b in content_list
        if b.get("type") in ("text", "title")
        and b.get("page_idx", 9999) < EARLY_PAGES
        and (b.get("text") or "").strip()
    )
    if not early:
        return None
    prompt = (
        "Below are the first pages of a parsed document. Determine whether they contain "
        "a printed Table of Contents (Contents, Index, Sommaire, etc.). If yes, extract "
        "every entry in order with: title, stated page number if printed (else null), "
        "and indent level (1=top, 2=sub, 3=sub-sub, 4=deepest). Drop entries that are "
        "clearly running headers/footers, page-number-only lines, or non-TOC text.\n\n"
        + early[:80_000]
    )
    resp = _client.models.generate_content(
        model=GEMINI_2_5_FLASH,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_DocTocResult,
        ),
    )
    r = _DocTocResult.model_validate_json(resp.text)
    return r.entries if r.found and r.entries else None


def match_doc_toc_to_skeleton(
    doc_toc: list[DocTocEntry], skeleton: list[SkeletonEntry]
) -> list[int | None]:
    prompt = (
        "Match each entry in A (a document's printed Table of Contents) to the single "
        "best corresponding entry in B (a heading skeleton automatically extracted from "
        "the same document). Match by title similarity — A titles are usually fuller "
        "('Chapter 5: Backpropagation') while B may be terser ('Backpropagation'). When "
        "a heading appears multiple times in B, prefer the one whose pdfPage is closest "
        "to A's statedPage offset by typical front-matter (~5-30 pages). Return null "
        "when no entry in B clearly corresponds — do NOT force a match.\n\n"
        f"A (doc TOC, {len(doc_toc)} entries):\n"
        f"{json.dumps([d.model_dump() for d in doc_toc])}\n\n"
        f"B (heading skeleton, {len(skeleton)} entries, indexed 0..{len(skeleton) - 1}):\n"
        f"{json.dumps([s.model_dump() for s in skeleton])}"
    )
    resp = _client.models.generate_content(
        model=GEMINI_2_5_FLASH,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_MatchResult,
        ),
    )
    return _MatchResult.model_validate_json(resp.text).skeleton_indices


def build_from_doc_toc(
    uid: str,
    title_id: str,
    doc_toc: list[DocTocEntry],
    skeleton: list[SkeletonEntry],
) -> list[TocEntry]:
    matches = match_doc_toc_to_skeleton(doc_toc, skeleton)
    seen: Counter = Counter()
    out: list[TocEntry] = []
    for d, m in zip(doc_toc, matches):
        if m is not None and 0 <= m < len(skeleton):
            s = skeleton[m]
            out.append(
                TocEntry(
                    title=d.title,
                    level=d.level,
                    pdfPage=s.pdfPage,
                    anchor=s.anchor,
                )
            )
            continue
        hits = vector_index.query(uid, title_id, d.title, k=3)
        if not hits:
            continue
        page_idx = min(int(h["pageIdx"]) for h in hits)
        out.append(
            TocEntry(
                title=d.title,
                level=d.level,
                pdfPage=page_idx + 1,
                anchor=_slugify(d.title, seen),
            )
        )
    return out


def prune_skeleton(skeleton: list[SkeletonEntry]) -> list[TocEntry]:
    if not skeleton:
        return []
    prompt = (
        "Below is a raw heading skeleton extracted from a parsed document. It may "
        "contain 100+ candidates including section headings, mid-paragraph emphasis, "
        "captions, duplicates, and fine-grained sub-sub items. Produce a clean, "
        "navigable Table of Contents by returning the indices of entries that "
        "represent meaningful section breaks a reader would want in a sidebar. Drop "
        "noise. Preserve order. Aim for the depth a print TOC would have.\n\n"
        f"Skeleton ({len(skeleton)} entries, indexed 0..{len(skeleton) - 1}):\n"
        f"{json.dumps([s.model_dump() for s in skeleton])}"
    )
    resp = _client.models.generate_content(
        model=GEMINI_3_1_FLASH_LITE,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_PruneResult,
        ),
    )
    keep = _PruneResult.model_validate_json(resp.text).keep_indices
    return [
        TocEntry(**skeleton[i].model_dump()) for i in keep if 0 <= i < len(skeleton)
    ]


def extract_toc(
    uid: str, title_id: str, content_list: list[dict]
) -> tuple[list[TocEntry], Literal["doc", "skeleton"]]:
    skeleton = heading_skeleton(content_list)
    doc_toc = detect_doc_toc(content_list)
    if doc_toc:
        return build_from_doc_toc(uid, title_id, doc_toc, skeleton), "doc"
    return prune_skeleton(skeleton), "skeleton"
