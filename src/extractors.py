"""
extractors.py
-------------
Text extraction from CV files: PDF, Word (.docx), and image (via OCR.Space).

Each extractor takes a file path and returns plain text.
On error, returns a string starting with a known error prefix so callers
can detect failures.
"""

import os
import PyPDF2
from docx import Document
import requests


# ---------- Error prefixes (used by app.py to detect failure) ----------
PDF_ERROR = "PDF read error:"
WORD_ERROR = "Word read error:"
OCR_ERROR = "OCR error:"


# ---------- PDF ----------
def extract_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file."""
    text_parts = []
    try:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
    except Exception as e:
        return f"{PDF_ERROR} {e}"
    return "\n".join(text_parts).strip()


# ---------- Word ----------
def extract_from_docx(file_path: str) -> str:
    """Extract text from a Word (.docx) file."""
    try:
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs]
        return "\n".join(paragraphs).strip()
    except Exception as e:
        return f"{WORD_ERROR} {e}"


# ---------- Image (OCR.Space) ----------
def extract_from_image(file_path: str, api_key: str) -> str:
    """
    Extract text from an image using OCR.Space.

    Requires a free API key: https://ocr.space/ocrapi
    """
    if not api_key:
        return f"{OCR_ERROR} OCR_SPACE_KEY not set in .env"

    url = "https://api.ocr.space/parse/image"
    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                url,
                files={"file": f},
                data={
                    "apikey": api_key,
                    "language": "eng",
                    "isOverlayRequired": False,
                    "OCREngine": 2,  # better for documents
                },
                timeout=30,
            )
        result = response.json()
    except Exception as e:
        return f"{OCR_ERROR} {e}"

    if result.get("IsErroredOnProcessing"):
        err = result.get("ErrorMessage") or result.get("ErrorDetails") or "unknown"
        return f"{OCR_ERROR} {err}"

    pages = result.get("ParsedResults") or []
    return "\n".join(p.get("ParsedText", "") for p in pages).strip()


# ---------- Router ----------
def extract_text(file_path: str, ocr_api_key: str = "") -> str:
    """
    Dispatch to the right extractor based on file extension.

    Returns extracted text, or a string starting with one of the *_ERROR
    prefixes on failure, or 'Unsupported format: ...' for unknown types.
    """
    if not file_path or not os.path.exists(file_path):
        return "File not found."

    ext = file_path.lower().rsplit(".", 1)[-1]

    if ext == "pdf":
        return extract_from_pdf(file_path)
    if ext in ("doc", "docx"):
        return extract_from_docx(file_path)
    if ext in ("jpg", "jpeg", "png", "bmp", "webp"):
        return extract_from_image(file_path, ocr_api_key)

    return f"Unsupported format: .{ext}"


def is_extraction_error(text: str) -> bool:
    """Return True if the text is an error message, not real content."""
    if not text:
        return True
    return text.startswith((PDF_ERROR, WORD_ERROR, OCR_ERROR, "Unsupported format", "File not found"))