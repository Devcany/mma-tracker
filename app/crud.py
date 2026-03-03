from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models, schemas


# Athlete
def get_athlete_by_telegram(db: Session, telegram_id: int):
    return db.query(models.Athlete).filter(models.Athlete.telegram_id == telegram_id).first()


def get_athlete(db: Session, athlete_id: int):
    return db.query(models.Athlete).filter(models.Athlete.id == athlete_id).first()


def create_athlete(db: Session, athlete: schemas.AthleteCreate):
    db_athlete = models.Athlete(**athlete.model_dump())
    db.add(db_athlete)
    db.commit()
    db.refresh(db_athlete)
    return db_athlete


# Sessions
def create_session(db: Session, athlete_id: int, session: schemas.SessionCreate):
    from datetime import datetime
    rounds_data = session.rounds
    session_data = session.model_dump(exclude={"rounds", "date_override"})
    db_session = models.TrainingSession(athlete_id=athlete_id, **session_data)
    if session.date_override:
        db_session.trained_on = datetime.combine(session.date_override, datetime.min.time())
    db.add(db_session)
    db.flush()

    for r in rounds_data:
        db_round = models.Round(session_id=db_session.id, **r.model_dump())
        db.add(db_round)

    db.commit()
    db.refresh(db_session)
    return db_session


def get_sessions(db: Session, athlete_id: int, limit: int = 20):
    return (
        db.query(models.TrainingSession)
        .filter(models.TrainingSession.athlete_id == athlete_id)
        .order_by(models.TrainingSession.logged_at.desc())
        .limit(limit)
        .all()
    )


def get_stats(db: Session, athlete_id: int) -> schemas.AthleteStats:
    sessions = db.query(models.TrainingSession).filter(
        models.TrainingSession.athlete_id == athlete_id
    ).all()

    if not sessions:
        return schemas.AthleteStats(
            total_sessions=0, total_minutes=0, avg_intensity=0.0,
            disciplines={}, last_session=None
        )

    total_minutes = sum(s.duration_minutes for s in sessions)
    avg_intensity = sum(s.intensity for s in sessions) / len(sessions)
    disciplines = {}
    for s in sessions:
        disciplines[s.discipline] = disciplines.get(s.discipline, 0) + 1
    last_session = max(s.logged_at for s in sessions)

    return schemas.AthleteStats(
        total_sessions=len(sessions),
        total_minutes=total_minutes,
        avg_intensity=round(avg_intensity, 1),
        disciplines=disciplines,
        last_session=last_session,
    )
