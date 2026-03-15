from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId


def document_doc(
    user_id: ObjectId,
    filename: str,
    original_name: str,
    file_url: str,
    extracted_text: Optional[str] = None,
) -> dict:
    return {
        "user": user_id,
        "filename": filename,
        "originalName": original_name,
        "fileUrl": file_url,
        "extractedText": extracted_text or "",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }


def document_response(doc: dict, text_preview: Optional[str] = None) -> dict:
    out = {
        "id": str(doc["_id"]),
        "filename": doc["filename"],
    }
    if text_preview is not None:
        out["textPreview"] = text_preview
    return out
