
from pathlib import Path
import fitz  # PyMuPDF
from docx import Document


def extract_pdf(file_path):
    """Extract text from a text-based PDF."""
    pages = []

    with fitz.open(file_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text")

            pages.append({
                "page": page_number,
                "text": text.strip()
            })

    return pages


def extract_docx(file_path):
    """Extract paragraphs from a DOCX document."""
    document = Document(file_path)
    paragraphs = []

    for paragraph_number, paragraph in enumerate(
        document.paragraphs, start=1
    ):
        text = paragraph.text.strip()

        if text:
            paragraphs.append({
                "paragraph": paragraph_number,
                "text": text,
                "style": paragraph.style.name
            })

    return paragraphs


def extract_document(file_path):
    """Choose the appropriate parser based on file extension."""
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".pdf":
        return {
            "filename": path.name,
            "format": "pdf",
            "content": extract_pdf(path)
        }

    if extension == ".docx":
        return {
            "filename": path.name,
            "format": "docx",
            "content": extract_docx(path)
        }

    raise ValueError("Only PDF and DOCX files are supported.")
