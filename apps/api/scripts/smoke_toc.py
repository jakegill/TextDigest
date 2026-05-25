"""One-off smoke test: run the rewritten extract_toc against a real
content_list.json and print the resulting TOC.

Drop a content_list.json file at apps/api/scripts/fixtures/content_list.json
(easiest: download from GCS at users/<uid>/titles/<titleId>/content_list.json),
then:

    uv run --no-sync python scripts/smoke_toc.py

You need GOOGLE_APPLICATION_CREDENTIALS / ADC set up for the Vertex Gemini call.
"""

import json
from pathlib import Path

from src.services.titles.toc import extract_toc, heading_skeleton

FIXTURE = Path(__file__).parent / "fixtures" / "content_list.json"


def main() -> None:
    if not FIXTURE.exists():
        raise SystemExit(
            f"missing {FIXTURE}. Drop a content_list.json there and rerun."
        )

    blocks = json.loads(FIXTURE.read_text())
    print(f"Loaded {len(blocks)} blocks from {FIXTURE.name}")

    skeleton = heading_skeleton(blocks)
    print(f"Heading skeleton: {len(skeleton)} entries")
    print("First 5 skeleton entries (truth source for pages):")
    for s in skeleton[:5]:
        print(f"  L{s.level}  p{s.pdfPage:>4}  {s.title}")
    print()

    entries, source = extract_toc("smoke-uid", "smoke-title", blocks)
    print(f"extract_toc returned {len(entries)} entries from source='{source}'")
    print()

    last_page = 0
    out_of_order = 0
    for e in entries:
        marker = "  " if e.pdfPage >= last_page else " !"
        print(f"{marker} L{e.level}  p{e.pdfPage:>4}  {e.title}")
        if e.pdfPage < last_page:
            out_of_order += 1
        last_page = max(last_page, e.pdfPage)

    print()
    print(f"out-of-order pages: {out_of_order}")
    print(f"pages span: {entries[0].pdfPage if entries else 0} .. "
          f"{entries[-1].pdfPage if entries else 0}")


if __name__ == "__main__":
    main()
