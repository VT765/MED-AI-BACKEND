from typing import Optional

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None


class ChatMessageOut(BaseModel):
    role: str
    content: str
    timestamp: str


class ChatMessageResponse(BaseModel):
    session_id: str
    reply: str
    timestamp: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessageOut]
