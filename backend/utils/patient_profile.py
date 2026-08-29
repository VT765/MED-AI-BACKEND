"""
Shared helper to turn a user's saved onboarding profile into a compact,
human-readable "patient profile" facts block. Used by the chat router (to keep
personal details in mind during conversation) and the report path (to interpret
lab results in the context of the patient).

Returns only the *facts*; each caller appends its own behavioural instruction
(chat personalises its guidance, report keeps its JSON-only contract).
"""

from datetime import datetime, timezone

# Human-readable labels for the onboarding health-condition keys
# (must match the keys saved by PUT /api/profile in routers/profile.py).
CONDITION_LABELS = {
    "diabetes": "Diabetes",
    "hypertension": "Hypertension (high blood pressure)",
    "asthma": "Asthma",
    "thyroid": "Thyroid disorder",
    "heartDisease": "Heart disease",
    "otherConditions": "Other chronic condition",
    "allergies": "Allergies",
    "medications": "Currently taking medication",
    "surgeries": "Past surgery",
    "familyHistory_diabetes": "Family history: diabetes",
    "familyHistory_hypertension": "Family history: hypertension",
    "familyHistory_heartDisease": "Family history: heart disease",
    "familyHistory_cancer": "Family history: cancer",
    "familyHistory_asthma": "Family history: asthma",
    "familyHistory_other": "Family history: other",
}


def calc_age(dob: str) -> int | None:
    """Best-effort age (years) from a date-of-birth string in common formats."""
    if not dob or not dob.strip():
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            born = datetime.strptime(dob.strip(), fmt)
        except ValueError:
            continue
        today = datetime.now(timezone.utc)
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if 0 < age < 120:
            return age
    return None


def build_patient_profile_facts(profile: dict | None) -> str:
    """
    Build a compact facts block from a saved onboarding profile.
    Returns "" if there is no meaningful profile data to share.
    """
    profile = profile or {}
    if not profile:
        return ""

    demographics: list[str] = []
    age = calc_age(profile.get("dob", "") or "")
    if age is not None:
        demographics.append(f"Age: {age}")
    if profile.get("gender"):
        demographics.append(f"Sex: {profile['gender']}")
    if profile.get("bloodGroup"):
        demographics.append(f"Blood group: {profile['bloodGroup']}")
    if profile.get("height"):
        demographics.append(f"Height: {profile['height']} cm")
    if profile.get("weight"):
        demographics.append(f"Weight: {profile['weight']} kg")
    if profile.get("bmi"):
        demographics.append(f"BMI: {profile['bmi']}")
    if profile.get("activityLevel"):
        demographics.append(f"Activity level: {profile['activityLevel']}")

    conditions: list[str] = []
    for key, val in (profile.get("conditions") or {}).items():
        if not isinstance(val, dict) or not val.get("yes"):
            continue
        label = CONDITION_LABELS.get(key, key)
        details = (val.get("details") or "").strip()
        conditions.append(f"{label}: {details}" if details else label)

    if not demographics and not conditions:
        return ""

    parts = ["PATIENT PROFILE (from the user's saved health profile):"]
    name = (profile.get("fullName") or "").strip()
    if name:
        parts.append(f"- Name: {name}")
    if demographics:
        parts.append("- " + " | ".join(demographics))
    if conditions:
        parts.append("- Relevant health background:")
        parts.extend(f"    • {c}" for c in conditions)
    return "\n".join(parts)
