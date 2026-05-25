import io

import pypdfium2 as pdfium
from google import genai
from google.genai import types

from ...dependencies import PROJECT_ID
from ...models.titles import CoverMetadata
from .constants import GEMINI_2_5_FLASH

VERTEX_LOCATION = "us-central1"

_client = genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


def render_first_page_png(pdf_bytes: bytes) -> bytes:
    pdf = pdfium.PdfDocument(pdf_bytes)
    page = pdf[0]
    pil = page.render().to_pil()
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def extract_metadata(cover_png: bytes) -> CoverMetadata:
    response = _client.models.generate_content(
        model=GEMINI_2_5_FLASH,
        contents=[
            types.Part.from_bytes(data=cover_png, mime_type="image/png"),
            "Extract the book or document title and the primary author shown on this cover page. "
            "If no author is visible, return an empty string.",
            "The output should be in title case; Examples: 'Text Like This', 'The Lord of the Rings'"
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CoverMetadata,
        ),
    )
    return CoverMetadata.model_validate_json(response.text)
