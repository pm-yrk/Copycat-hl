from __future__ import annotations

from contextlib import contextmanager
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from .settings import get_settings

settings = get_settings()


def _normalise_database_url(raw: str) -> str:
    """Return a SQLAlchemy/psycopg URL from common Postgres URL formats."""
    raw = (raw or '').strip()
    if not raw:
        return ''
    if raw.startswith('postgres://'):
        return 'postgresql+psycopg://' + raw[len('postgres://'):]
    if raw.startswith('postgresql://'):
        return 'postgresql+psycopg://' + raw[len('postgresql://'):]
    return raw


def _resolve_database_url() -> str:
    """Resolve the database URL without silently falling back to localhost.

    Render services do not share environment variables automatically. A newly
    created worker can therefore miss DATABASE_URL while the API service still
    has it. The previous local default made that look like a Postgres outage at
    127.0.0.1:5432. This resolver accepts the common Supabase/Render variable
    names and gives a clear deployment error when none are present.
    """
    candidates = [
        settings.database_url,
        settings.supabase_db_url,
        settings.postgres_url,
        settings.postgres_prisma_url,
        settings.postgres_url_non_pooling,
        os.getenv('DATABASE_URL', ''),
        os.getenv('SUPABASE_DB_URL', ''),
        os.getenv('POSTGRES_URL', ''),
        os.getenv('POSTGRES_PRISMA_URL', ''),
        os.getenv('POSTGRES_URL_NON_POOLING', ''),
    ]
    for candidate in candidates:
        resolved = _normalise_database_url(candidate)
        if resolved:
            return resolved
    raise RuntimeError(
        'DATABASE_URL is not set. In Render, copy the same DATABASE_URL/Supabase '
        'Postgres connection string used by hwt-api onto this service. Copycat '
        'will not fall back to localhost in deployed workers.'
    )


DATABASE_URL = _resolve_database_url()

# Render runs several separate containers/processes for the API, collector, and cron jobs.
# Supabase's pooler can reject new connections when each container keeps its own local
# SQLAlchemy pool open. NullPool opens a connection only for the query/transaction and
# closes it immediately afterwards, which prevents Copycat from exhausting the Supabase
# pooler session limit while still keeping the app responsive.
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    pool_pre_ping=True,
    pool_recycle=60,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def execute_schema_file(path: str) -> None:
    sql = open(path, 'r', encoding='utf-8').read()
    with engine.begin() as conn:
        conn.execute(text(sql))


def fetch_all(sql: str, params: dict | None = None) -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
        return [dict(r) for r in rows]


def fetch_one(sql: str, params: dict | None = None) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None


def execute(sql: str, params: dict | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})
