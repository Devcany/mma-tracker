from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from . import crud, schemas
from .database import get_db

router = APIRouter()


# ── Users ─────────────────────────────────────────────────────────────────────

@router.post("/users", response_model=schemas.UserOut, status_code=201)
def register_user(user: schemas.UserCreate, db: DBSession = Depends(get_db)):
    if crud.get_user(db, user.id):
        raise HTTPException(status_code=409, detail="User already registered")
    return crud.create_user(db, user)


@router.get("/users/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: str, db: DBSession = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


class RoleUpdate(BaseModel):
    role: schemas.UserRole


@router.patch("/users/{user_id}/role", response_model=schemas.UserOut)
def update_role(user_id: str, body: RoleUpdate, db: DBSession = Depends(get_db)):
    user = crud.update_user_role(db, user_id, body.role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=schemas.SessionOut, status_code=201)
def create_session(session: schemas.SessionCreate, db: DBSession = Depends(get_db)):
    if not crud.get_user(db, session.user_id):
        raise HTTPException(status_code=404, detail="User not found — register first")
    return crud.create_session(db, session)


@router.get("/sessions/{user_id}", response_model=list[schemas.SessionOut])
def list_sessions(
    user_id: str,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: DBSession = Depends(get_db),
):
    if not crud.get_user(db, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return crud.get_sessions(db, user_id, from_date, to_date, type, limit)


@router.get("/sessions/{user_id}/last", response_model=schemas.SessionOut)
def last_session(
    user_id: str,
    type: Optional[str] = Query(None),
    db: DBSession = Depends(get_db),
):
    if not crud.get_user(db, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    session = crud.get_last_session(db, user_id, type)
    if not session:
        raise HTTPException(status_code=404, detail="No sessions found")
    return session
