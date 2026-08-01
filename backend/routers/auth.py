from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import ServerSelectionTimeoutError, PyMongoError

from database import get_db
from deps import get_current_user
from models.user import user_doc
from schemas.auth import AuthResponse, LoginRequest, MeResponse, MeUserResponse, SignupRequest, UserResponse
from utils.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
async def signup(body: SignupRequest):
    db = get_db()
    existing_email = await db.users.find_one({"email": body.email.strip().lower()})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )
    existing_username = await db.users.find_one({"username": body.username.strip()})
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken",
        )
    hashed = hash_password(body.password)
    doc = user_doc(
        username=body.username,
        email=body.email,
        password_hash=hashed,
    )
    result = await db.users.insert_one(doc)
    user_id = str(result.inserted_id)
    user_doc_inserted = await db.users.find_one({"_id": result.inserted_id})
    token = create_token(user_id)
    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user_id,
            username=user_doc_inserted["username"],
            email=user_doc_inserted["email"],
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    try:
        db = get_db()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    try:
        user = await db.users.find_one(
            {"email": body.email.strip().lower()},
            projection={"password": 1, "username": 1, "email": 1, "_id": 1},
        )
    except ServerSelectionTimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Database is temporarily unavailable. Please try again later.",
        )
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not verify_password(body.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_token(str(user["_id"]))
    return AuthResponse(
        token=token,
        user=UserResponse(
            id=str(user["_id"]),
            username=user["username"],
            email=user["email"],
        ),
    )


@router.get("/me", response_model=MeResponse)
async def get_me(user: dict = Depends(get_current_user)):
    created_at = user.get("createdAt")
    username = user.get("username")
    phone = user.get("phone", "")
    profile_complete = bool(username and user.get("email"))
    return MeResponse(
        user=MeUserResponse(
            id=str(user["_id"]),
            username=username,
            email=user["email"],
            createdAt=created_at.isoformat() if created_at else None,
            phone=phone or "",
            authProvider="email",
            profileComplete=profile_complete,
        )
    )
