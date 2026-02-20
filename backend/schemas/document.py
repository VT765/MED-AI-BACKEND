from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    message: str
    document: dict
