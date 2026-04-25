"""
SQLite database setup via SQLAlchemy.
One table: incidents — append-only log of every resolved incident.
Used by Learning Node (write) and Diagnosis Node (read for context).
"""
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///incidents.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class IncidentRow(Base):
    __tablename__ = "incidents"

    id                = Column(String, primary_key=True)
    pipeline_id       = Column(String, nullable=False, index=True)
    timestamp         = Column(DateTime, nullable=False)
    anomaly_type      = Column(String, nullable=False, index=True)
    root_cause        = Column(Text, nullable=False)
    strategy_executed = Column(String, nullable=False)
    outcome           = Column(String, nullable=False)   # success | failed | skipped
    human_approved    = Column(Boolean, nullable=False, default=False)
    created_at        = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    """Create tables if they don't exist."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Return a new SQLAlchemy session."""
    return Session(engine)
