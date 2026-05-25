"""One-off smoke test: hit the patched MinerU title-leveling step against
Vertex with a tiny fake title dict and print the result.

Run from apps/api/:
    uv run --no-sync python scripts/smoke_title_levels.py
"""

import google.auth
from google.auth.transport.requests import Request as GoogleRequest
from mineru.utils.llm_aided import _request_title_levels

VERTEX_LOCATION = "us-central1"

SAMPLE_TITLES = {
    "0": ["Part I: Foundations", 30, 1],
    "1": ["Chapter 1: Getting Started", 22, 2],
    "2": ["1.1 Installation", 17, 3],
    "3": ["1.2 Hello World", 17, 4],
    "4": ["Chapter 2: Going Deeper", 22, 8],
    "5": ["2.1 Architecture", 17, 9],
    "6": ["Part II: Advanced", 30, 20],
    "7": ["Chapter 3: Performance", 22, 21],
}


def main() -> None:
    creds, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(GoogleRequest())

    cfg = {
        "api_key": creds.token,
        "base_url": (
            f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com"
            f"/v1beta1/projects/{project}/locations/{VERTEX_LOCATION}"
            "/endpoints/openapi/"
        ),
        "model": "google/gemini-2.5-flash",
    }

    print(f"Sending {len(SAMPLE_TITLES)} titles to Vertex Gemini via OpenAI compat...")
    result = _request_title_levels(cfg, SAMPLE_TITLES)
    print(f"Result type: {type(result).__name__}")
    print(f"Result: {result}")
    if result is None:
        raise SystemExit("FAILED: returned None")
    expected = set(range(len(SAMPLE_TITLES)))
    if set(result.keys()) != expected:
        raise SystemExit(f"FAILED: id mismatch (got {set(result.keys())}, want {expected})")
    if not all(v in (1, 2, 3, 4) for v in result.values()):
        raise SystemExit(f"FAILED: invalid level (got {list(result.values())})")
    print("OK — structured output works end-to-end against Vertex.")


if __name__ == "__main__":
    main()
