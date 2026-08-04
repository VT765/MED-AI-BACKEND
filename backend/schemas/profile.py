from typing import Optional, Dict
from pydantic import BaseModel, Field


class HealthCondition(BaseModel):
    yes: bool = False
    details: str = ""


class ProfileSaveRequest(BaseModel):
    fullName: str = ""
    dob: str = ""
    gender: str = ""
    bloodGroup: str = ""
    phone: str = ""
    height: str = ""
    weight: str = ""
    activityLevel: str = ""
    conditions: Dict[str, HealthCondition] = Field(default_factory=dict)


class ProfileResponse(BaseModel):
    fullName: str = ""
    dob: str = ""
    gender: str = ""
    bloodGroup: str = ""
    phone: str = ""
    height: str = ""
    weight: str = ""
    bmi: Optional[str] = None
    activityLevel: str = ""
    conditions: Dict[str, HealthCondition] = Field(default_factory=dict)
    onboardingDone: bool = False
    profileComplete: int = 0  # percentage 0-100
