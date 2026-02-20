from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    documentId: str


class ChatResponse(BaseModel):
    answer: str
