"""
Chat router — conversational AI doctor powered by Groq (llama-3.1-8b-instant).
Single active session per user, stored in MongoDB `chat_sessions` collection.
Guest chat is stateless — no history or data is stored.
"""

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import edge_tts
import requests
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from config import GROQ_API_KEY
from database import get_db
from deps import get_current_user, get_optional_user
from schemas.chat import ChatHistoryResponse, ChatMessageOut, ChatMessageRequest, ChatMessageResponse
from utils.patient_profile import build_patient_profile_facts

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── Groq config ──────────────────────────────────────────────
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25MB — Groq's transcription upload limit
# NOTE: llama-3.1-8b-instant was decommissioned on Groq; use a currently-available model.
GROQ_MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.65
MAX_HISTORY_MESSAGES = 20
# Kept modest to stay within Groq free-tier TPM limits; ample for short replies
# since reasoning_effort is "low".
MAX_TOKENS = 800
# Retry short rate-limit (429) bursts instead of failing the request outright.
MAX_RATE_LIMIT_RETRIES = 2
MAX_RATE_LIMIT_WAIT = 8.0  # seconds — cap so a slow reply never hangs the UI


# ── System prompts ───────────────────────────────────────────
_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT_PATH = _PROMPT_DIR / "chat_prompt.md"
_GUEST_PROMPT_PATH = _PROMPT_DIR / "guest_chat_prompt.md"
_FALLBACK_PROMPT = "You are Med-AI, a friendly doctor. Always reply in the same language the patient writes in (Hindi for Hindi, Hinglish for Hinglish, English for English). Use simple words. Never diagnose or prescribe."
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


def _salvage_failed_generation(failed_generation) -> str:
    """
    Recover the assistant's text from a Groq `failed_generation` payload.

    gpt-oss models sometimes emit a normal reply wrapped as a phantom tool call
    (e.g. {"name": "assistant", "arguments": {"content": "..."}}), which Groq
    rejects with a `tool_use_failed` error. The real answer is inside that
    payload — extract and return it so the chat still works.
    """
    if not isinstance(failed_generation, str):
        return ""
    try:
        obj = json.loads(failed_generation)
    except json.JSONDecodeError:
        return failed_generation.strip()

    if isinstance(obj, dict):
        args = obj.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = None
        if isinstance(args, dict) and args.get("content"):
            return str(args["content"]).strip()
        if obj.get("content"):
            return str(obj["content"]).strip()
    return ""


def _parse_retry_after(response, data) -> float:
    """
    Determine how long to wait before retrying a 429. Prefers the standard
    `Retry-After` header, then the "try again in Xs" hint in Groq's message,
    then a small default. Capped by MAX_RATE_LIMIT_WAIT.
    """
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(float(header), MAX_RATE_LIMIT_WAIT)
        except ValueError:
            pass
    msg = ((data or {}).get("error", {}) or {}).get("message", "") if isinstance(data, dict) else ""
    match = re.search(r"try again in ([\d.]+)s", msg)
    if match:
        try:
            return min(float(match.group(1)) + 0.3, MAX_RATE_LIMIT_WAIT)
        except ValueError:
            pass
    return 3.0


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
    if "gpt-oss" in GROQ_MODEL:
        # gpt-oss models reason before answering; keep it light so the token
        # budget goes to the actual reply, not the hidden reasoning trace.
        payload["reasoning_effort"] = "low"

    # On a rate-limit (429), Groq tells us how long to wait (usually a few
    # seconds). Retry a couple of times so short bursts self-heal instead of
    # surfacing a raw error to the user.
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
            data = response.json()

            if response.status_code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                wait = _parse_retry_after(response, data)
                time.sleep(wait)
                continue

            if response.status_code != 200:
                err = data.get("error", {}) or {}
                # gpt-oss sometimes returns a valid reply wrapped as a bogus tool
                # call. Groq flags it as `tool_use_failed`; recover the text.
                if err.get("code") == "tool_use_failed" and err.get("failed_generation"):
                    salvaged = _salvage_failed_generation(err["failed_generation"])
                    if salvaged:
                        return salvaged
                if response.status_code == 429:
                    raise HTTPException(
                        status_code=429,
                        detail="The AI is a bit busy right now. Please wait a few seconds and try again.",
                    )
                error_msg = err.get("message", "Unknown Groq API error")
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


# ── Patient profile context ──────────────────────────────────

def _build_patient_profile_context(user: dict) -> str:
    """
    Build a patient-profile system message from the user's saved onboarding
    profile so the AI keeps their personal details in mind during the chat.
    Returns "" if no profile has been saved yet.
    """
    facts = build_patient_profile_facts(user.get("profile"))
    if not facts:
        return ""
    instruction = (
        "\nKeep this in mind for every reply. Personalise your guidance to this profile "
        "(age, sex, existing conditions, allergies and current medications). Never suggest "
        "anything that conflicts with a listed allergy or condition. Do not restate the whole "
        "profile back to the user."
    )
    return facts + instruction


# ── Conversation stage ───────────────────────────────────────

def _get_conversation_stage(messages: list[dict]) -> str:
    """
    Determine conversation stage based on number of user messages.
    - 0–2 user messages → 'questioning' (ask follow-ups, gather info)
    - 3+  user messages → 'guidance' (provide advice and suggestions)
    """
    user_count = sum(1 for m in messages if m.get("role") == "user")
    return "guidance" if user_count >= 3 else "questioning"


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

    # Inject the patient's saved onboarding profile so the AI doctor keeps
    # their personal details (age, sex, conditions, allergies, meds) in mind.
    patient_context = _build_patient_profile_context(user)
    if patient_context:
        groq_messages.append({"role": "system", "content": patient_context})

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


@router.post("/stream")
async def send_message_stream(body: ChatMessageRequest, user: dict = Depends(get_current_user)):
    """
    Streaming variant of send_message. Emits Server-Sent Events:
      data: {"delta": "..."}    — incremental reply text
      data: {"done": true, "session_id": "...", "timestamp": "..."}
      data: {"error": "..."}    — terminal error
    The full reply is persisted to the session when the stream completes.
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="AI chat is not available. GROQ_API_KEY is not configured.")

    db = get_db()
    user_id = str(user["_id"])

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

    history = session.get("messages", [])
    recent = history[-MAX_HISTORY_MESSAGES:] if len(history) > MAX_HISTORY_MESSAGES else history
    stage = _get_conversation_stage(history)
    system_prompt = _build_system_prompt(stage, len(history) == 0)

    groq_messages = [{"role": "system", "content": system_prompt}]
    patient_context = _build_patient_profile_context(user)
    if patient_context:
        groq_messages.append({"role": "system", "content": patient_context})
    for msg in recent:
        groq_messages.append({"role": msg["role"], "content": msg["content"]})
    groq_messages.append({"role": "user", "content": body.message})

    payload = {
        "model": GROQ_MODEL,
        "messages": groq_messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": True,
    }
    if "gpt-oss" in GROQ_MODEL:
        payload["reasoning_effort"] = "low"

    async def event_gen():
        import httpx

        full: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                async with client.stream(
                    "POST",
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        detail = "AI service error. Please try again."
                        if response.status_code == 429:
                            detail = "The AI is a bit busy right now. Please wait a few seconds and try again."
                        yield f"data: {json.dumps({'error': detail})}\n\n"
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        try:
                            delta = json.loads(chunk)["choices"][0]["delta"].get("content")
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        if delta:
                            full.append(delta)
                            yield f"data: {json.dumps({'delta': delta})}\n\n"
        except httpx.TimeoutException:
            yield f"data: {json.dumps({'error': 'AI service timed out. Please try again.'})}\n\n"
            return
        except httpx.HTTPError:
            yield f"data: {json.dumps({'error': 'Could not connect to the AI service.'})}\n\n"
            return

        reply_text = "".join(full).strip()
        if not reply_text:
            yield f"data: {json.dumps({'error': 'AI returned an empty response. Please try again.'})}\n\n"
            return

        reply_timestamp = _now_iso()
        await db.chat_sessions.update_one(
            {"_id": session["_id"]},
            {
                "$push": {"messages": {"$each": [user_msg, {"role": "assistant", "content": reply_text, "timestamp": reply_timestamp}]}},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )
        yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'timestamp': reply_timestamp})}\n\n"

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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


# ── Voice transcription (speech-to-text) ─────────────────────

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    user: dict | None = Depends(get_optional_user),
):
    """
    Transcribe a recorded audio clip to text using Groq Whisper.
    Available in both guest and authenticated chat so users can speak
    their question instead of typing. Returns {"text": "..."}.
    """
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Voice input is not available. GROQ_API_KEY is not configured.",
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="No audio received. Please try recording again.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio is too long (max 25MB). Please record a shorter clip.")

    try:
        response = requests.post(
            GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (file.filename or "recording.webm", audio_bytes, file.content_type or "audio/webm")},
            # No language hint — let Whisper auto-detect so Hindi and other
            # languages are transcribed as spoken, matching the assistant's
            # mirror-the-user's-language behavior.
            data={"model": WHISPER_MODEL, "response_format": "json"},
            timeout=60,
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Transcription timed out. Please try again.")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail="Could not connect to the transcription service.")

    if response.status_code != 200:
        try:
            msg = response.json().get("error", {}).get("message", "Transcription failed")
        except ValueError:
            msg = "Transcription failed"
        raise HTTPException(status_code=502, detail=f"Transcription error: {msg}")

    try:
        text = (response.json().get("text") or "").strip()
    except ValueError:
        raise HTTPException(status_code=502, detail="Transcription returned an invalid response.")

    return {"text": text}


class TTSRequest(BaseModel):
    text: str


@router.post("/tts")
async def synthesize_speech(body: TTSRequest):
    """
    Text-to-speech for voice mode. Returns MP3 audio bytes.

    Uses Microsoft Edge neural voices via edge-tts (free, multilingual) —
    browser speechSynthesis is unreliable across Chromium forks, and the
    reply may be in Hindi or English so the voice is picked per request.
    """
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text to speak.")
    # Keep requests bounded — voice replies shouldn't be essays anyway.
    text = text[:3500]

    # Devanagari → Hindi neural voice; otherwise Indian-English voice.
    # Male voices to match the doctor avatar.
    voice = "hi-IN-MadhurNeural" if re.search(r"[ऀ-ॿ]", text) else "en-IN-PrabhatNeural"

    try:
        communicate = edge_tts.Communicate(text, voice)
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
    except Exception:
        raise HTTPException(status_code=502, detail="Voice synthesis failed. Please try again.")

    if not audio:
        raise HTTPException(status_code=502, detail="Voice synthesis returned no audio.")

    return Response(content=bytes(audio), media_type="audio/mpeg")


# ══════════════════════════════════════════════════════════════
# GUEST CHAT ENDPOINTS — No authentication required
# Stateless: no history stored, no personalization, each message
# is independent. Only a session_id is issued for frontend tracking.
# ══════════════════════════════════════════════════════════════

def _generate_guest_session_id() -> str:
    """Generate a temporary guest session ID: guest_xxxxxxxxx."""
    return f"guest_{uuid.uuid4().hex[:12]}"


class GuestChatRequest(ChatMessageRequest):
    """Same as ChatMessageRequest — reuse existing schema."""
    pass


@router.post("/guest", response_model=ChatMessageResponse)
async def guest_send_message(body: GuestChatRequest):
    """
    Send a guest message and get an AI reply. No authentication required.
    Stateless — no conversation history is stored or sent to the LLM.
    Each message is treated as an independent question.
    """
    session_id = body.session_id or _generate_guest_session_id()
    now = _now_iso()

    # Build messages array — system prompt + current user message only (no history)
    system_prompt = _load_guest_system_prompt()
    groq_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.message},
    ]

    # Call LLM
    reply_text = _call_groq(groq_messages)

    reply_timestamp = _now_iso()

    return ChatMessageResponse(
        session_id=session_id,
        reply=reply_text,
        timestamp=reply_timestamp,
    )


@router.get("/guest/history", response_model=ChatHistoryResponse)
async def guest_get_history(session_id: str = ""):
    """
    Guest chat has no history — always returns empty.
    Kept for API compatibility with the frontend.
    """
    return ChatHistoryResponse(session_id=session_id or "", messages=[])


@router.post("/guest/new")
async def guest_new_chat():
    """Start a fresh guest chat session. Returns a new session ID only."""
    new_id = _generate_guest_session_id()
    return {"session_id": new_id, "message": "New guest chat session created"}
