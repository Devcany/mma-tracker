from datetime import date as date_type
from typing import Optional
from sqlalchemy.orm import Session as DBSession
from . import models, schemas


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user(db: DBSession, user_id: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


def create_user(db: DBSession, user: schemas.UserCreate) -> models.User:
    db_user = models.User(id=user.id, name=user.name, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user_role(db: DBSession, user_id: str, role: str) -> Optional[models.User]:
    user = get_user(db, user_id)
    if not user:
        return None
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def get_or_create_user(db: DBSession, user_id: str, name: str, role: str = "athlete") -> tuple[models.User, bool]:
    """Returns (user, created). Safe to call on every message."""
    user = get_user(db, user_id)
    if user:
        return user, False
    user = create_user(db, schemas.UserCreate(id=user_id, name=name, role=role))
    return user, True


# ── Sessions ──────────────────────────────────────────────────────────────────

def create_session(db: DBSession, session: schemas.SessionCreate) -> models.Session:
    db_session = models.Session(**session.model_dump())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


def get_sessions(
    db: DBSession,
    user_id: str,
    from_date: Optional[date_type] = None,
    to_date: Optional[date_type] = None,
    session_type: Optional[str] = None,
    limit: int = 50,
) -> list[models.Session]:
    q = db.query(models.Session).filter(models.Session.user_id == user_id)
    if from_date:
        q = q.filter(models.Session.date >= from_date)
    if to_date:
        q = q.filter(models.Session.date <= to_date)
    if session_type:
        q = q.filter(models.Session.session_type == session_type)
    return q.order_by(models.Session.date.desc(), models.Session.created_at.desc()).limit(limit).all()


def get_last_session(
    db: DBSession,
    user_id: str,
    session_type: Optional[str] = None,
) -> Optional[models.Session]:
    q = db.query(models.Session).filter(models.Session.user_id == user_id)
    if session_type:
        q = q.filter(models.Session.session_type == session_type)
    return q.order_by(models.Session.date.desc(), models.Session.created_at.desc()).first()
