from datetime import datetime, date
from typing import Optional, Literal
from pydantic import BaseModel, Field

# Spec-defined session_type enum
SessionType = Literal[
    "sparring", "drilling", "clinch", "groundwork",
    "muay_thai", "wrestling", "bjj", "s&c", "open"
]

UserRole = Literal["athlete", "coach"]


# ── Users ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    id: str                          # Telegram chat_id
    name: str
    role: UserRole = "athlete"


class UserOut(BaseModel):
    id: str
    name: str
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Sessions ──────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    user_id: str
    date: date
    session_type: SessionType
    duration_min: Optional[int] = None
    rounds: Optional[int] = None
    intensity_rpe: Optional[int] = Field(None, ge=1, le=10)
    notes: str = ""
    raw_input: str                   # always required — original unmodified text


class SessionOut(BaseModel):
    id: int
    user_id: str
    date: date
    session_type: str
    duration_min: Optional[int]
    rounds: Optional[int]
    intensity_rpe: Optional[int]
    notes: str
    raw_input: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Groups (schema-ready, inactive in MVP) ────────────────────────────────────

class GroupCreate(BaseModel):
    name: str
    coach_id: str


class GroupOut(BaseModel):
    id: int
    name: str
    coach_id: str
    created_at: datetime

    model_config = {"from_attributes": True}
