from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError, PyMongoError

from database import get_db
from utils.security import decode_token

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
):
    if not credentials or not credentials.scheme == "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized, no token",
        )
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized, token failed",
        )
    user_id = payload.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized, token failed",
        )
    try:
        db = get_db()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
    except ServerSelectionTimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Database is temporarily unavailable. Please try again later.",
        )
    except PyMongoError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {e}",
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized, user not found",
        )
    return user


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
):
    """Same as get_current_user but returns None instead of 401 when not authenticated."""
    if not credentials or not credentials.scheme == "Bearer":
        return None
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        return None
    user_id = payload.get("id")
    if not user_id:
        return None
    try:
        db = get_db()
        user = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
    return user
