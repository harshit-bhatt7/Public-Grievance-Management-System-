"""
Database engine, session factory, and declarative base.

Future modules (grievances, audit logs, AI analysis, etc.) will import
`Base` from here to register their models, and `get_db` as a FastAPI
dependency to obtain a request-scoped session.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # avoids stale connections after idle periods
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency that yields a database session and guarantees
    it is closed after the request finishes, even on error.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
