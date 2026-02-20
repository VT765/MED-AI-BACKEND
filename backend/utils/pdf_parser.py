from pathlib import Path

from pypdf import PdfReader


def extract_text_from_pdf(file_path: str | Path) -> str:
    reader = PdfReader(str(file_path))
    text_parts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text_parts.append(t)
    return "\n".join(text_parts)
