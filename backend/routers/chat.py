from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI

from config import OPENAI_API_KEY
from database import get_db
from deps import get_current_user
from schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])

DISCLAIMER = "\n\n**Disclaimer: This is not medical advice. Consult a licensed professional.**"


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    if not body.question or not body.documentId:
        raise HTTPException(status_code=400, detail="Question and Document ID required")

    db = get_db()
    try:
        doc_id = ObjectId(body.documentId)
    except Exception:
        raise HTTPException(status_code=404, detail="Document not found")

    document = await db.documents.find_one({"_id": doc_id})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if str(document["user"]) != str(user["_id"]):
        raise HTTPException(status_code=401, detail="Not authorized to access this document")

    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI chat is not available. Add OPENAI_API_KEY to your .env to enable it.",
        )

    context_text = (document.get("extractedText") or "")[:10000]
    client = OpenAI(api_key=OPENAI_API_KEY)
    completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a helpful medical assistant. Answer the user's question based on the provided document text. Disclaimer: This is not medical advice. Consult a licensed professional.",
            },
            {
                "role": "user",
                "content": f"Document Text: {context_text}\n\nQuestion: {body.question}",
            },
        ],
        model="gpt-3.5-turbo",
    )
    answer = completion.choices[0].message.content or ""
    return ChatResponse(answer=answer + DISCLAIMER)
