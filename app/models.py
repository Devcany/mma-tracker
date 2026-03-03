from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base


class Athlete(Base):
    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    weight_class = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("TrainingSession", back_populates="athlete", cascade="all, delete-orphan")


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id"), nullable=False)
    discipline = Column(String(50), nullable=False)  # BJJ, Boxing, Wrestling, MMA, etc.
    duration_minutes = Column(Integer, nullable=False)
    intensity = Column(Integer, nullable=False)  # 1-10
    notes = Column(Text)
    logged_at = Column(DateTime, default=datetime.utcnow)
    trained_on = Column(DateTime, nullable=True)  # actual training date (voice logs)

    athlete = relationship("Athlete", back_populates="sessions")
    rounds = relationship("Round", back_populates="session", cascade="all, delete-orphan")


class Round(Base):
    __tablename__ = "rounds"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("training_sessions.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    duration_seconds = Column(Integer, default=300)  # 5 min default
    opponent_notes = Column(Text)

    session = relationship("TrainingSession", back_populates="rounds")
