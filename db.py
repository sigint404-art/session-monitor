"""
db.py  —  Database layer for the session monitor.
Reads all connection details from credentials.py.
To switch databases, only edit credentials.py.
"""

from __future__ import annotations
import os
from datetime import datetime, date, time as time_type
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String,
    Date, Time, Boolean
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

import credentials as cfg


# ─── Build connection URL from credentials.py ────────────────────────────────

def _build_url() -> str:
    t = cfg.DB_TYPE.lower()
    if t == "sqlite":
        # Make sure the parent folder exists
        db_path = os.path.abspath(cfg.SQLITE_PATH)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return f"sqlite:///{db_path}"
    elif t == "mysql":
        return (
            f"mysql+pymysql://{cfg.MYSQL_USER}:{cfg.MYSQL_PASSWORD}"
            f"@{cfg.MYSQL_HOST}:{cfg.MYSQL_PORT}/{cfg.MYSQL_DB}"
            "?charset=utf8mb4"
        )
    elif t == "postgresql":
        return (
            f"postgresql+psycopg2://{cfg.PG_USER}:{cfg.PG_PASSWORD}"
            f"@{cfg.PG_HOST}:{cfg.PG_PORT}/{cfg.PG_DB}"
        )
    else:
        raise ValueError(
            f"Unknown DB_TYPE '{cfg.DB_TYPE}' in credentials.py. "
            "Use 'sqlite', 'mysql', or 'postgresql'."
        )


# ─── SQLAlchemy engine + session factory ─────────────────────────────────────

engine       = create_engine(_build_url(), echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


# ─── Table definition ────────────────────────────────────────────────────────

class SessionEntry(Base):
    """
    sessions table
    ┌────────────┬──────────┬─────────────────────────────────────────┐
    │ column     │ type     │ notes                                   │
    ├────────────┼──────────┼─────────────────────────────────────────┤
    │ id         │ INTEGER  │ primary key, auto-increment             │
    │ date       │ DATE     │ date folder was detected                │
    │ time       │ TIME     │ time folder was detected                │
    │ foldername │ TEXT     │ name of the folder (unique)             │
    │ site       │ TEXT     │ site label, editable via dashboard      │
    │ isUpload   │ BOOLEAN  │ False by default; set True after upload │
    └────────────┴──────────┴─────────────────────────────────────────┘
    """
    __tablename__ = "sessions"

    id         = Column(Integer,      primary_key=True, autoincrement=True)
    date       = Column(Date,         nullable=False)
    time       = Column(Time,         nullable=False)
    foldername = Column(String(255),  nullable=False, unique=True)
    site       = Column(String(255),  nullable=False, default="")
    isUpload   = Column(Boolean,      nullable=False, default=False)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "date":       str(self.date),
            "time":       str(self.time),
            "foldername": self.foldername,
            "site":       self.site,
            "isUpload":   self.isUpload,
        }


# ─── One-time setup ──────────────────────────────────────────────────────────

def init_db() -> None:
    """Create the sessions table if it does not exist yet."""
    Base.metadata.create_all(engine)


# ─── CRUD operations ─────────────────────────────────────────────────────────

def folder_exists(foldername: str) -> bool:
    """Return True if this foldername is already in the database."""
    with SessionLocal() as db:
        return (
            db.query(SessionEntry)
              .filter_by(foldername=foldername)
              .first() is not None
        )


def add_session(
    foldername: str,
    site: str = "",
    detected_at: Optional[datetime] = None,
) -> SessionEntry:
    """Insert a new row. Returns the created SessionEntry."""
    now = detected_at or datetime.now()
    with SessionLocal() as db:
        entry = SessionEntry(
            date=now.date(),
            time=now.time().replace(microsecond=0),
            foldername=foldername,
            site=site or cfg.DEFAULT_SITE,
            isUpload=False,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry


def get_all_sessions() -> list[dict]:
    """Return all rows as a list of dicts, newest first."""
    with SessionLocal() as db:
        rows = (
            db.query(SessionEntry)
              .order_by(SessionEntry.id.desc())
              .all()
        )
        return [r.to_dict() for r in rows]


def get_session(session_id: int) -> Optional[dict]:
    """Return one row as a dict, or None if not found."""
    with SessionLocal() as db:
        row = db.get(SessionEntry, session_id)
        return row.to_dict() if row else None


def update_session(session_id: int, **fields) -> Optional[dict]:
    """
    Update any combination of: date, time, foldername, site, isUpload.
    Returns updated dict, or None if id not found.
    """
    allowed = {"date", "time", "foldername", "site", "isUpload"}
    with SessionLocal() as db:
        row = db.get(SessionEntry, session_id)
        if not row:
            return None
        for key, val in fields.items():
            if key in allowed:
                setattr(row, key, val)
        db.commit()
        db.refresh(row)
        return row.to_dict()


def delete_session(session_id: int) -> bool:
    """Delete a row by id. Returns True if deleted, False if not found."""
    with SessionLocal() as db:
        row = db.get(SessionEntry, session_id)
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True


def mark_uploaded(session_id: int) -> Optional[dict]:
    """Shortcut: set isUpload = True for the given id."""
    return update_session(session_id, isUpload=True)