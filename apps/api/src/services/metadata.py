from google import genai
from google.genai import types

from ..dependencies import PROJECT_ID
from ..models.titles import CoverMetadata

GEMINI_MODEL = "gemini-2.5-flash"
VERTEX_LOCATION = "us-central1"

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


def extract_from_cover(cover_png: bytes) -> CoverMetadata:
    response = _client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=cover_png, mime_type="image/png"),
            "Extract the book or document title and the primary author shown on this cover page. "
            "If no author is visible, return an empty string.",
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CoverMetadata,
        ),
    )
    return CoverMetadata.model_validate_json(response.text)
