"""
Chat router — conversational AI doctor powered by Groq (llama-3.1-8b-instant).
Single active session per user, stored in MongoDB `chat_sessions` collection.
"""

from datetime import datetime, timezone
from pathlib import Path

import requests
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from config import GROQ_API_KEY
from database import get_db
from deps import get_current_user
from schemas.chat import ChatHistoryResponse, ChatMessageOut, ChatMessageRequest, ChatMessageResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── Groq config ──────────────────────────────────────────────
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"
TEMPERATURE = 0.5
MAX_HISTORY_MESSAGES = 20
# Keep replies short — 256 tokens ≈ 3-4 sentences
MAX_TOKENS = 256

# ── System prompt ────────────────────────────────────────────
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "chat_prompt.md"


def _load_system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "You are Med-AI, a friendly medical assistant. Answer in 2-3 short sentences using simple English. Never diagnose or prescribe."


SYSTEM_PROMPT = _load_system_prompt()


# ── Helpers ──────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_or_create_session(db, user_id: str) -> dict:
    """Get the user's active chat session, or create a new one."""
    session = await db.chat_sessions.find_one(
        {"user_id": user_id, "active": True},
        sort=[("created_at", -1)],
    )
    if session:
        return session

    new_session = {
        "user_id": user_id,
        "active": True,
        "messages": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.chat_sessions.insert_one(new_session)
    new_session["_id"] = result.inserted_id
    return new_session


def _call_groq(messages: list[dict]) -> str:
    """Call Groq API with message list. Returns assistant reply text."""
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI chat is not available. GROQ_API_KEY is not configured.",
        )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        data = response.json()

        if response.status_code != 200:
            error_msg = data.get("error", {}).get("message", "Unknown Groq API error")
            raise HTTPException(status_code=502, detail=f"AI service error: {error_msg}")

        if "choices" not in data or not data["choices"]:
            raise HTTPException(status_code=502, detail="AI returned an empty response")

        return data["choices"][0].get("message", {}).get("content", "").strip()
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="AI service timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail="Could not connect to AI service.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# ── Routes ───────────────────────────────────────────────────

@router.post("", response_model=ChatMessageResponse)
async def send_message(body: ChatMessageRequest, user: dict = Depends(get_current_user)):
    """Send a message and get an AI reply."""
    db = get_db()
    user_id = str(user["_id"])

    # Get or create session
    if body.session_id:
        try:
            session = await db.chat_sessions.find_one({
                "_id": ObjectId(body.session_id),
                "user_id": user_id,
                "active": True,
            })
        except Exception:
            session = None
        if not session:
            session = await _get_or_create_session(db, user_id)
    else:
        session = await _get_or_create_session(db, user_id)

    session_id = str(session["_id"])
    now = _now_iso()

    user_msg = {"role": "user", "content": body.message, "timestamp": now}

    # Build messages array for Groq (system + recent history + new message)
    history = session.get("messages", [])
    recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history

    groq_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in recent:
        groq_messages.append({"role": msg["role"], "content": msg["content"]})
    groq_messages.append({"role": "user", "content": body.message})

    # Call LLM
    reply_text = _call_groq(groq_messages)

    reply_timestamp = _now_iso()
    assistant_msg = {"role": "assistant", "content": reply_text, "timestamp": reply_timestamp}

    # Save both messages
    await db.chat_sessions.update_one(
        {"_id": session["_id"]},
        {
            "$push": {"messages": {"$each": [user_msg, assistant_msg]}},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )

    return ChatMessageResponse(
        session_id=session_id,
        reply=reply_text,
        timestamp=reply_timestamp,
    )


@router.get("/history", response_model=ChatHistoryResponse)
async def get_history(user: dict = Depends(get_current_user)):
    """Get the user's active chat session history."""
    db = get_db()
    user_id = str(user["_id"])

    session = await db.chat_sessions.find_one(
        {"user_id": user_id, "active": True},
        sort=[("created_at", -1)],
    )

    if not session:
        return ChatHistoryResponse(session_id="", messages=[])

    messages_out = [
        ChatMessageOut(role=m["role"], content=m["content"], timestamp=m["timestamp"])
        for m in session.get("messages", [])
    ]

    return ChatHistoryResponse(
        session_id=str(session["_id"]),
        messages=messages_out,
    )


@router.post("/new")
async def new_chat(user: dict = Depends(get_current_user)):
    """Clear current session and start fresh."""
    db = get_db()
    user_id = str(user["_id"])

    await db.chat_sessions.update_many(
        {"user_id": user_id, "active": True},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}},
    )

    session = await _get_or_create_session(db, user_id)
    return {"session_id": str(session["_id"]), "message": "New chat session created"}
