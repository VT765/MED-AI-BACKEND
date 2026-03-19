"""
OCR utilities for extracting text from medical report images.
Uses Tesseract via pytesseract; preprocessing via OpenCV.
"""

import os
from pathlib import Path

try:
    import cv2
    import pytesseract

    # Tesseract path for Apple Silicon (override via TESSERACT_CMD env if needed)
    _tesseract_cmd = os.getenv("TESSERACT_CMD")
    if _tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
    elif Path("/opt/homebrew/bin/tesseract").exists():
        pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"

    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


def run_ocr(image_path: str | Path) -> str:
    """
    Extract text from an image using Tesseract OCR.
    Uses grayscale + threshold preprocessing for better accuracy on medical reports.

    Args:
        image_path: Path to image file (JPEG, PNG, etc.)

    Returns:
        Extracted text string
    """
    if not _OCR_AVAILABLE:
        raise RuntimeError(
            "OCR dependencies (opencv-python-headless, pytesseract) not installed. "
            "Install with: pip install opencv-python-headless pytesseract"
        )

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError("Image not found or unsupported format")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
    text = pytesseract.image_to_string(thresh)
    return text or ""
