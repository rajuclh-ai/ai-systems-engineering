"""
SQLAlchemy models and session management.
Stores one row per completed review for the learning node.
"""
import os
from contextlib import contextmanager
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./reviews.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class ReviewRow(Base):
    __tablename__ = "reviews"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    thread_id    = Column(String, unique=True, index=True)
    pr_url       = Column(String)
    repo         = Column(String, index=True)         # owner/repo — for future context lookup
    verdict      = Column(String)                     # APPROVE | REQUEST_CHANGES | NEEDS_DISCUSSION
    finding_count= Column(Integer, default=0)
    high_count   = Column(Integer, default=0)
    medium_count = Column(Integer, default=0)
    low_count    = Column(Integer, default=0)
    summary      = Column(Text)
    created_at   = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
