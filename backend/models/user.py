from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId


def user_doc(username: str, email: str, password_hash: str, phone: Optional[str] = None) -> dict:
    return {
        "username": username.strip(),
        "email": email.strip().lower(),
        "password": password_hash,
        "phone": phone or None,
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }


def user_response(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "username": doc["username"],
        "email": doc["email"],
        "createdAt": doc.get("createdAt"),
    }
