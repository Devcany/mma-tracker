from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# Athlete
class AthleteCreate(BaseModel):
    telegram_id: int
    name: str
    weight_class: Optional[str] = None


class AthleteOut(BaseModel):
    id: int
    telegram_id: int
    name: str
    weight_class: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# Round
class RoundCreate(BaseModel):
    round_number: int
    duration_seconds: int = 300
    opponent_notes: Optional[str] = None


class RoundOut(RoundCreate):
    id: int
    session_id: int

    model_config = {"from_attributes": True}


# Training Session
class SessionCreate(BaseModel):
    discipline: str = Field(..., examples=["BJJ", "Boxing", "Wrestling", "MMA", "Kickboxing"])
    duration_minutes: int = Field(..., ge=1, le=480)
    intensity: int = Field(..., ge=1, le=10)
    notes: Optional[str] = None
    rounds: List[RoundCreate] = []


class SessionOut(BaseModel):
    id: int
    athlete_id: int
    discipline: str
    duration_minutes: int
    intensity: int
    notes: Optional[str]
    logged_at: datetime
    rounds: List[RoundOut] = []

    model_config = {"from_attributes": True}


# Stats
class AthleteStats(BaseModel):
    total_sessions: int
    total_minutes: int
    avg_intensity: float
    disciplines: dict
    last_session: Optional[datetime]
