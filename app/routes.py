from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from . import crud, schemas
from .database import get_db

router = APIRouter(prefix="/api/v1")


@router.post("/athletes", response_model=schemas.AthleteOut, status_code=201)
def register_athlete(athlete: schemas.AthleteCreate, db: Session = Depends(get_db)):
    existing = crud.get_athlete_by_telegram(db, athlete.telegram_id)
    if existing:
        raise HTTPException(status_code=409, detail="Athlete already registered")
    return crud.create_athlete(db, athlete)


@router.get("/athletes/{telegram_id}", response_model=schemas.AthleteOut)
def get_athlete(telegram_id: int, db: Session = Depends(get_db)):
    athlete = crud.get_athlete_by_telegram(db, telegram_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return athlete


@router.post("/athletes/{telegram_id}/sessions", response_model=schemas.SessionOut, status_code=201)
def log_session(telegram_id: int, session: schemas.SessionCreate, db: Session = Depends(get_db)):
    athlete = crud.get_athlete_by_telegram(db, telegram_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found — register first")
    return crud.create_session(db, athlete.id, session)


@router.get("/athletes/{telegram_id}/sessions", response_model=list[schemas.SessionOut])
def list_sessions(telegram_id: int, limit: int = 20, db: Session = Depends(get_db)):
    athlete = crud.get_athlete_by_telegram(db, telegram_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return crud.get_sessions(db, athlete.id, limit)


@router.get("/athletes/{telegram_id}/stats", response_model=schemas.AthleteStats)
def get_stats(telegram_id: int, db: Session = Depends(get_db)):
    athlete = crud.get_athlete_by_telegram(db, telegram_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return crud.get_stats(db, athlete.id)
