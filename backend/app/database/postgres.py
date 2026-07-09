"""
SQLAlchemy engine / session setup for direct PostgreSQL access to the
Supabase database. This is used for real DDL (table creation) and any
query that's easier to express with SQLAlchemy than the Supabase REST client.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from app.config import settings

# pool_pre_ping avoids stale-connection errors against managed Postgres (Supabase)
#
# NOTE: this app is configured for a DIRECT connection to the Supabase
# database (port 5432), not the pgbouncer pooler (port 6543). Direct
# connections support a normal SQLAlchemy QueuePool and prepared statements
# without issue. Supabase requires SSL on direct connections, so we enforce
# sslmode=require here in case it isn't already present in DATABASE_URL.
_connect_args = {}
if "sslmode" not in settings.DATABASE_URL:
    _connect_args["sslmode"] = "require"

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    future=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context-manager version for use outside of FastAPI request handling
    (e.g. in init_db.py or scripts)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_connection() -> bool:
    """Used on FastAPI startup to fail fast if the DB is unreachable."""
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
