import io

import pypdfium2 as pdfium


def render_first_page_png(pdf_bytes: bytes) -> bytes:
    pdf = pdfium.PdfDocument(pdf_bytes)
    page = pdf[0]
    pil = page.render().to_pil()
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()
