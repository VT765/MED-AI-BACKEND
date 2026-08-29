"""
Report analysis route: OCR/extract text → LLM → structured JSON.
Now persists analysis results to MongoDB for authenticated users.
"""

import tempfile
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

import requests
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from config import LLM_SERVICE_URL, MAX_FILE_SIZE
from database import get_db
from deps import get_current_user, get_optional_user
from utils.pdf_parser import extract_text_from_pdf
from utils.patient_profile import build_patient_profile_facts

router = APIRouter(prefix="/api/reports", tags=["reports"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/jpg"}
ALLOWED_PDF_TYPE = "application/pdf"
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def _extract_text_from_file(file_path: Path, content_type: str) -> str:
    """Extract text from PDF or image. PDF uses pypdf; images use Tesseract OCR."""
    if content_type == ALLOWED_PDF_TYPE or file_path.suffix.lower() == ".pdf":
        return extract_text_from_pdf(file_path)

    if content_type in ALLOWED_IMAGE_TYPES or file_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        from utils.ocr_utils import run_ocr
        return run_ocr(file_path)

    raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF or image (JPEG/PNG).")


def _call_llm_service(text: str, patient_context: str = "") -> dict:
    """Send extracted text to LLM service. Returns analysis dict or error dict."""
    try:
        response = requests.post(
            f"{LLM_SERVICE_URL.rstrip('/')}/analyze",
            json={"text": text, "patient_context": patient_context},
            timeout=90,
        )
    except requests.RequestException as e:
        return {"error": "Failed to connect to LLM service", "details": str(e)}

    if response.status_code != 200:
        return {"error": f"LLM service returned {response.status_code}", "details": response.text[:500]}

    try:
        data = response.json()
    except ValueError:
        return {"error": "Invalid JSON from LLM service", "details": response.text[:500]}

    if "error" in data:
        return data

    return data


@router.post("/analyze")
async def analyze_report(
    file: UploadFile = File(...),
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Analyze a medical report (PDF or image).
    Flow: Extract text (OCR for images, pypdf for PDF) → LLM → validated JSON.
    If the user is authenticated, persist the result to MongoDB.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Supported formats: PDF, JPG, PNG")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    content_type = (file.content_type or "").lower()
    if content_type not in {ALLOWED_PDF_TYPE, "image/jpeg", "image/png", "image/jpg"} and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file type")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        extracted_text = _extract_text_from_file(tmp_path, content_type)
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {str(e)}") from e
    finally:
        tmp_path.unlink(missing_ok=True)

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in the document")

    # Personalise report interpretation with the authenticated user's profile.
    patient_context = build_patient_profile_facts(user.get("profile")) if user else ""
    result = _call_llm_service(extracted_text, patient_context)

    if "error" in result:
        # Persist a failed record if user is authenticated
        if user:
            db = get_db()
            await db.report_analyses.insert_one({
                "user_id": str(user["_id"]),
                "filename": file.filename or "unknown",
                "status": "Failed",
                "analysis": None,
                "error": result.get("error", "Unknown error"),
                "created_at": datetime.now(timezone.utc),
            })
        detail = result.get("details", result["error"])
        raise HTTPException(status_code=502, detail=str(detail) if not isinstance(detail, str) else detail)

    analysis = result.get("analysis")
    if not analysis:
        raise HTTPException(status_code=502, detail="LLM service returned no analysis")

    # Persist successful analysis for authenticated users
    if user:
        db = get_db()
        await db.report_analyses.insert_one({
            "user_id": str(user["_id"]),
            "filename": file.filename or "unknown",
            "status": "Completed",
            "analysis": analysis,
            "created_at": datetime.now(timezone.utc),
        })

    return analysis


# ── History endpoints (authenticated) ────────────────────────


@router.get("/history")
async def list_reports(user: dict = Depends(get_current_user)):
    """List all past report analyses for the authenticated user, newest first."""
    db = get_db()
    user_id = str(user["_id"])

    cursor = db.report_analyses.find(
        {"user_id": user_id},
        sort=[("created_at", -1)],
    )

    reports = []
    async for doc in cursor:
        reports.append({
            "report_id": str(doc["_id"]),
            "filename": doc.get("filename", "Unknown"),
            "status": doc.get("status", "Unknown"),
            "created_at": doc["created_at"].isoformat() if hasattr(doc.get("created_at", ""), "isoformat") else str(doc.get("created_at", "")),
        })

    return {"reports": reports}


@router.get("/history/{report_id}")
async def get_report(report_id: str, user: dict = Depends(get_current_user)):
    """Get a single past report analysis by ID."""
    db = get_db()
    user_id = str(user["_id"])

    try:
        doc = await db.report_analyses.find_one({
            "_id": ObjectId(report_id),
            "user_id": user_id,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "report_id": str(doc["_id"]),
        "filename": doc.get("filename", "Unknown"),
        "status": doc.get("status", "Unknown"),
        "analysis": doc.get("analysis"),
        "created_at": doc["created_at"].isoformat() if hasattr(doc.get("created_at", ""), "isoformat") else str(doc.get("created_at", "")),
    }
