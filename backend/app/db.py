from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from .settings import get_settings

settings = get_settings()

# Render runs several separate containers/processes for the API, collector, and cron jobs.
# Supabase's pooler can reject new connections when each container keeps its own local
# SQLAlchemy pool open. NullPool opens a connection only for the query/transaction and
# closes it immediately afterwards, which prevents Copycat from exhausting the Supabase
# pooler session limit while still keeping the app responsive.
engine = create_engine(
    settings.database_url,
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
