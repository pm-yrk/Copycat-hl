from __future__ import annotations

import gzip
import json
import logging
import os
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import engine

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

ARCHIVE_TABLES = {
    'copycat_live_events': {'ts_col': 'ts_ms', 'keep_days_env': 'COPYCAT_LIVE_EVENTS_KEEP_DAYS', 'default_keep_days': 2},
    'owned_wallet_fills': {'ts_col': 'ts_ms', 'keep_days_env': 'COPYCAT_OWNED_FILLS_KEEP_DAYS', 'default_keep_days': 14},
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except Exception:
        return default


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute(text("""
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_schema='public' AND table_name=:table
        )
    """), {'table': table}).scalar())


def _r2_client():
    # Optional dependency. Only imported if cold archive is enabled.
    import boto3  # type: ignore

    endpoint = os.getenv('R2_ENDPOINT_URL')
    access_key = os.getenv('R2_ACCESS_KEY_ID')
    secret_key = os.getenv('R2_SECRET_ACCESS_KEY')
    if not endpoint or not access_key or not secret_key:
        raise RuntimeError('R2_ENDPOINT_URL, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY are required for cold archive')
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv('R2_REGION', 'auto'),
    )


def _json_default(value: Any) -> str:
    return str(value)


def _archive_rows_to_r2(table: str, rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    bucket = os.getenv('R2_BUCKET_NAME')
    if not bucket:
        raise RuntimeError('R2_BUCKET_NAME is required for cold archive')

    now = datetime.now(timezone.utc)
    prefix = os.getenv('R2_ARCHIVE_PREFIX', 'copycat-archive').strip('/')
    key = f"{prefix}/{table}/year={now.year:04d}/month={now.month:02d}/day={now.day:02d}/{int(time.time())}-{len(rows)}.jsonl.gz"

    buf = BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as gz:
        for row in rows:
            gz.write((json.dumps(row, default=_json_default, separators=(',', ':')) + '\n').encode('utf-8'))

    _r2_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=buf.getvalue(),
        ContentType='application/jsonl',
        ContentEncoding='gzip',
    )
    return key


def run_cold_archive_once() -> dict[str, Any]:
    """Move old heavy rows out of Supabase hot Postgres and into Cloudflare R2.

    This is disabled by default. It is the long-term free/low-cost path:
    Supabase stores current/hot rows; R2 stores compressed cold history.
    """
    if not _env_bool('COPYCAT_COLD_ARCHIVE_ENABLED', False):
        return {'status': 'disabled', 'message': 'Set COPYCAT_COLD_ARCHIVE_ENABLED=true after R2 is configured.'}

    limit = max(100, _env_int('COPYCAT_COLD_ARCHIVE_BATCH_ROWS', 2000))
    archived: dict[str, Any] = {}

    for table, cfg in ARCHIVE_TABLES.items():
        keep_days = max(0, _env_int(str(cfg['keep_days_env']), int(cfg['default_keep_days'])))
        cutoff_ms = int((time.time() - keep_days * 86400) * 1000)
        ts_col = str(cfg['ts_col'])
        with engine.begin() as conn:
            if not _table_exists(conn, table):
                archived[table] = {'status': 'missing'}
                continue
            rows = [dict(r) for r in conn.execute(text(f"""
                SELECT * FROM public.{table}
                WHERE {ts_col} < :cutoff_ms
                ORDER BY {ts_col} ASC
                LIMIT :limit
            """), {'cutoff_ms': cutoff_ms, 'limit': limit}).mappings().all()]
            if not rows:
                archived[table] = {'status': 'empty'}
                continue
            key = _archive_rows_to_r2(table, rows)
            # Delete by ids when possible; otherwise by timestamp batch boundary.
            if 'id' in rows[0]:
                ids = [r['id'] for r in rows]
                deleted = conn.execute(text(f"DELETE FROM public.{table} WHERE id = ANY(:ids)"), {'ids': ids}).rowcount or 0
            else:
                max_ts = max(int(r.get(ts_col) or 0) for r in rows)
                deleted = conn.execute(text(f"DELETE FROM public.{table} WHERE {ts_col} <= :max_ts AND {ts_col} < :cutoff_ms"), {'max_ts': max_ts, 'cutoff_ms': cutoff_ms}).rowcount or 0
            archived[table] = {'status': 'archived', 'rows': len(rows), 'deleted': int(deleted), 'r2_key': key}

    log.info('Cold archive complete: %s', archived)
    return {'status': 'ok', 'archived': archived}
