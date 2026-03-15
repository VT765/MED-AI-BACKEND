import time
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from config import MAX_FILE_SIZE, UPLOAD_DIR
from database import get_db
from deps import get_current_user
from models.document import document_doc, document_response
from utils.pdf_parser import extract_text_from_pdf

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_CONTENT = "application/pdf"
EXT = ".pdf"


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.lower().endswith("pdf"):
        raise HTTPException(status_code=400, detail="Error: PDFs Only!")
    if file.filename and not file.filename.lower().endswith(EXT):
        raise HTTPException(status_code=400, detail="Error: PDFs Only!")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    safe_name = f"file-{int(time.time() * 1000)}{EXT}"
    file_path = UPLOAD_DIR / safe_name
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        extracted_text = extract_text_from_pdf(file_path)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"File processing failed: {e}") from e

    file_url = f"uploads/{safe_name}"
    db = get_db()
    doc = document_doc(
        user_id=user["_id"],
        filename=safe_name,
        original_name=file.filename or "document.pdf",
        file_url=file_url,
        extracted_text=extracted_text,
    )
    result = await db.documents.insert_one(doc)
    document = await db.documents.find_one({"_id": result.inserted_id})
    text_preview = (document["extractedText"] or "")[:200] + "..."
    return {
        "message": "File uploaded and processed successfully",
        "document": document_response(document, text_preview=text_preview),
    }
