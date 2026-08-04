from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from deps import get_current_user
from schemas.profile import ProfileSaveRequest, ProfileResponse, HealthCondition

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _calc_bmi(height: str, weight: str) -> str | None:
    try:
        h = float(height) / 100
        w = float(weight)
        if h > 0 and w > 0:
            return f"{w / (h * h):.1f}"
    except (ValueError, ZeroDivisionError):
        pass
    return None


def _calc_profile_complete(profile: dict) -> int:
    """Calculate profile completion percentage based on filled fields."""
    fields = ["fullName", "dob", "gender", "height", "weight", "activityLevel"]
    optional_fields = ["bloodGroup", "phone"]
    total = len(fields) + len(optional_fields) + 1  # +1 for at least one condition answered
    filled = 0
    for f in fields:
        if profile.get(f):
            filled += 1
    for f in optional_fields:
        if profile.get(f):
            filled += 1
    # Check if any condition was answered (at least one "yes")
    conditions = profile.get("conditions", {})
    if any(c.get("yes", False) for c in conditions.values()):
        filled += 1
    return int((filled / total) * 100)


@router.put("")
async def save_profile(body: ProfileSaveRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    user_id = user["_id"]

    profile_data = body.model_dump()
    profile_data["bmi"] = _calc_bmi(body.height, body.weight)
    profile_data["onboardingDone"] = True
    profile_data["profileComplete"] = _calc_profile_complete(profile_data)
    profile_data["updatedAt"] = datetime.now(timezone.utc)

    # Convert conditions to plain dicts for MongoDB storage
    conditions_dict = {}
    for key, val in profile_data.get("conditions", {}).items():
        if isinstance(val, dict):
            conditions_dict[key] = val
        else:
            conditions_dict[key] = {"yes": val.yes, "details": val.details}
    profile_data["conditions"] = conditions_dict

    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"profile": profile_data, "updatedAt": datetime.now(timezone.utc)}},
    )

    return {"message": "Profile saved successfully", "profile": profile_data}


@router.get("", response_model=ProfileResponse)
async def get_profile(user: dict = Depends(get_current_user)):
    profile = user.get("profile")
    if not profile:
        return ProfileResponse()

    # Build response
    conditions = {}
    raw_conditions = profile.get("conditions", {})
    for key, val in raw_conditions.items():
        if isinstance(val, dict):
            conditions[key] = HealthCondition(
                yes=val.get("yes", False),
                details=val.get("details", ""),
            )
        else:
            conditions[key] = HealthCondition()

    return ProfileResponse(
        fullName=profile.get("fullName", ""),
        dob=profile.get("dob", ""),
        gender=profile.get("gender", ""),
        bloodGroup=profile.get("bloodGroup", ""),
        phone=profile.get("phone", ""),
        height=profile.get("height", ""),
        weight=profile.get("weight", ""),
        bmi=profile.get("bmi"),
        activityLevel=profile.get("activityLevel", ""),
        conditions=conditions,
        onboardingDone=profile.get("onboardingDone", False),
        profileComplete=profile.get("profileComplete", 0),
    )
