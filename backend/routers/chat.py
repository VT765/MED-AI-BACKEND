"""
Chat router — conversational AI doctor powered by Groq (llama-3.1-8b-instant).
Single active session per user, stored in MongoDB `chat_sessions` collection.
Guest sessions stored in `guest_chat_sessions` with auto-expiry.
"""

import uuid
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
TEMPERATURE = 0.65
MAX_HISTORY_MESSAGES = 20
MAX_TOKENS = 512

# Number of user messages before switching from questioning to guidance
GUIDANCE_THRESHOLD = 3

# ── System prompts ───────────────────────────────────────────
_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_PATH = _PROMPT_DIR / "chat_prompt.md"
_GUEST_PROMPT_PATH = _PROMPT_DIR / "guest_chat_prompt.md"
_FALLBACK_PROMPT = "You are Med-AI, a friendly doctor. Answer in simple English only. Never use Hindi or Hinglish. Never diagnose or prescribe."
_FALLBACK_GUEST_PROMPT = "You are Med-AI, an evidence-based medical assistant. The user is NOT authenticated. Provide general medical guidance only. Never personalize. End with a confidence level."


def _load_system_prompt() -> str:
    """Load authenticated system prompt fresh from file each time."""
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _FALLBACK_PROMPT


def _load_guest_system_prompt() -> str:
    """Load guest system prompt fresh from file each time."""
    try:
        return _GUEST_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _FALLBACK_GUEST_PROMPT


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


# ── Conversation stage ───────────────────────────────────────

def _get_conversation_stage(messages: list[dict]) -> str:
    """
    Determine conversation stage based on number of user messages.
    - 0–2 user messages → 'questioning' (ask follow-ups, gather info)
    - 3+  user messages → 'guidance' (provide advice and suggestions)
    """
    user_count = sum(1 for m in messages if m.get("role") == "user")
    return "guidance" if user_count >= GUIDANCE_THRESHOLD else "questioning"


def _build_system_prompt(stage: str, is_first_message: bool) -> str:
    """
    Build the system prompt with a stage hint appended.
    The base prompt in chat_prompt.md already describes both stages;
    the hint tells the LLM which stage to use right now.
    """
    hint = ""
    if stage == "questioning":
        hint = (
            "\n\n[CURRENT STAGE: QUESTIONING]\n"
            "You do NOT have enough information yet. "
            "Ask 1-2 short follow-up questions. Keep response to 2-3 lines. "
            "Do NOT give advice or medications yet."
        )
    else:
        hint = (
            "\n\n[CURRENT STAGE: GUIDANCE]\n"
            "You now have enough context from the patient. "
            "Provide helpful, specific guidance including self-care tips "
            "and OTC medicine suggestions (no dosage). "
            "Keep it conversational and natural."
        )

    return _load_system_prompt() + hint


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
    is_first_message = len(history) == 0

    # Determine conversation stage (questioning vs guidance)
    stage = _get_conversation_stage(history)
    system_prompt = _build_system_prompt(stage, is_first_message)

    groq_messages = [{"role": "system", "content": system_prompt}]
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


@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    """List all chat sessions for the authenticated user, newest first."""
    db = get_db()
    user_id = str(user["_id"])

    cursor = db.chat_sessions.find(
        {"user_id": user_id},
        sort=[("updated_at", -1)],
    )

    sessions = []
    async for session in cursor:
        messages = session.get("messages", [])
        # Derive title from the first user message
        title = "New conversation"
        for msg in messages:
            if msg.get("role") == "user":
                title = msg["content"][:60]
                break

        sessions.append({
            "session_id": str(session["_id"]),
            "title": title,
            "active": session.get("active", False),
            "message_count": len(messages),
            "created_at": session.get("created_at", "").isoformat() if hasattr(session.get("created_at", ""), "isoformat") else str(session.get("created_at", "")),
            "updated_at": session.get("updated_at", "").isoformat() if hasattr(session.get("updated_at", ""), "isoformat") else str(session.get("updated_at", "")),
        })

    return {"sessions": sessions}


@router.get("/sessions/{session_id}", response_model=ChatHistoryResponse)
async def get_session_history(session_id: str, user: dict = Depends(get_current_user)):
    """Get the message history for a specific session."""
    db = get_db()
    user_id = str(user["_id"])

    try:
        session = await db.chat_sessions.find_one({
            "_id": ObjectId(session_id),
            "user_id": user_id,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages_out = [
        ChatMessageOut(role=m["role"], content=m["content"], timestamp=m["timestamp"])
        for m in session.get("messages", [])
    ]

    return ChatHistoryResponse(
        session_id=str(session["_id"]),
        messages=messages_out,
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    """Permanently delete a chat session."""
    db = get_db()
    user_id = str(user["_id"])

    try:
        result = await db.chat_sessions.delete_one({
            "_id": ObjectId(session_id),
            "user_id": user_id,
        })
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"message": "Chat session deleted"}


# ══════════════════════════════════════════════════════════════
# GUEST CHAT ENDPOINTS — No authentication required
# ══════════════════════════════════════════════════════════════

def _generate_guest_session_id() -> str:
    """Generate a temporary guest session ID: guest_xxxxxxxxx."""
    return f"guest_{uuid.uuid4().hex[:12]}"


async def _get_or_create_guest_session(db, session_id: str | None) -> dict:
    """Get an existing guest session by ID, or create a new one."""
    if session_id:
        session = await db.guest_chat_sessions.find_one({"session_id": session_id})
        if session:
            return session

    new_id = _generate_guest_session_id()
    new_session = {
        "session_id": new_id,
        "messages": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.guest_chat_sessions.insert_one(new_session)
    return new_session


def _build_guest_system_prompt(stage: str) -> str:
    """Build guest system prompt with stage hint."""
    hint = ""
    if stage == "questioning":
        hint = (
            "\n\n[CURRENT STAGE: QUESTIONING]\n"
            "You do NOT have enough information yet. "
            "Ask 1-2 short follow-up questions. Keep response to 2-3 lines. "
            "Do NOT give advice or medications yet."
        )
    else:
        hint = (
            "\n\n[CURRENT STAGE: GUIDANCE]\n"
            "You now have enough context from the patient. "
            "Provide helpful, specific guidance including self-care tips "
            "and OTC medicine suggestions (no dosage). "
            "Keep it conversational and natural."
        )
    return _load_guest_system_prompt() + hint


class GuestChatRequest(ChatMessageRequest):
    """Same as ChatMessageRequest — reuse existing schema."""
    pass


@router.post("/guest", response_model=ChatMessageResponse)
async def guest_send_message(body: GuestChatRequest):
    """Send a guest message and get an AI reply. No authentication required."""
    db = get_db()

    session = await _get_or_create_guest_session(db, body.session_id)
    session_id = session["session_id"]
    now = _now_iso()

    user_msg = {"role": "user", "content": body.message, "timestamp": now}

    # Build messages array for Groq (guest prompt + history + new message)
    history = session.get("messages", [])
    recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history

    stage = _get_conversation_stage(history)
    system_prompt = _build_guest_system_prompt(stage)

    groq_messages = [{"role": "system", "content": system_prompt}]
    for msg in recent:
        groq_messages.append({"role": msg["role"], "content": msg["content"]})
    groq_messages.append({"role": "user", "content": body.message})

    # Call LLM
    reply_text = _call_groq(groq_messages)

    reply_timestamp = _now_iso()
    assistant_msg = {"role": "assistant", "content": reply_text, "timestamp": reply_timestamp}

    # Save both messages
    await db.guest_chat_sessions.update_one(
        {"session_id": session_id},
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


@router.get("/guest/history", response_model=ChatHistoryResponse)
async def guest_get_history(session_id: str = ""):
    """Get guest chat session history. No authentication required."""
    if not session_id:
        return ChatHistoryResponse(session_id="", messages=[])

    db = get_db()
    session = await db.guest_chat_sessions.find_one({"session_id": session_id})

    if not session:
        return ChatHistoryResponse(session_id="", messages=[])

    messages_out = [
        ChatMessageOut(role=m["role"], content=m["content"], timestamp=m["timestamp"])
        for m in session.get("messages", [])
    ]

    return ChatHistoryResponse(
        session_id=session["session_id"],
        messages=messages_out,
    )


@router.post("/guest/new")
async def guest_new_chat():
    """Start a fresh guest chat session. No authentication required."""
    db = get_db()
    session = await _get_or_create_guest_session(db, None)
    return {"session_id": session["session_id"], "message": "New guest chat session created"}
