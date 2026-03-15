from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    createdAt: Optional[str] = None
    phone: Optional[str] = None


class MeUserResponse(UserResponse):
    authProvider: str = "email"
    profileComplete: bool = False


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class MeResponse(BaseModel):
    user: MeUserResponse
