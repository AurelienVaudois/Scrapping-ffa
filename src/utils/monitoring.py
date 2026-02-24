from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Dict, Generator, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def ensure_monitoring_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS app_monitoring_events (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    session_id TEXT,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ok',
                    duration_ms INTEGER,
                    metadata JSONB
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_app_monitoring_events_created_at
                    ON app_monitoring_events (created_at DESC)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_app_monitoring_events_event_type
                    ON app_monitoring_events (event_type)
                """
            )
        )


def track_event(
    engine: Engine,
    event_type: str,
    session_id: Optional[str] = None,
    status: str = "ok",
    duration_ms: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        serialized_metadata = json.dumps(metadata) if metadata is not None else None
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO app_monitoring_events (session_id, event_type, status, duration_ms, metadata)
                    VALUES (:session_id, :event_type, :status, :duration_ms, CAST(:metadata AS JSONB))
                    """
                ),
                {
                    "session_id": session_id,
                    "event_type": event_type,
                    "status": status,
                    "duration_ms": duration_ms,
                    "metadata": serialized_metadata,
                },
            )
    except Exception as exc:
        logger.debug("Monitoring write skipped: %s", exc)


@contextmanager
def track_timing(
    engine: Engine,
    event_type: str,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator[None, None, None]:
    start = perf_counter()
    try:
        yield
        elapsed = int((perf_counter() - start) * 1000)
        track_event(
            engine=engine,
            event_type=event_type,
            session_id=session_id,
            status="ok",
            duration_ms=elapsed,
            metadata=metadata,
        )
    except Exception:
        elapsed = int((perf_counter() - start) * 1000)
        track_event(
            engine=engine,
            event_type=event_type,
            session_id=session_id,
            status="error",
            duration_ms=elapsed,
            metadata=metadata,
        )
        raise


def init_sentry() -> bool:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False

    try:
        import sentry_sdk
    except Exception:
        logger.warning("SENTRY_DSN set but sentry-sdk not installed")
        return False

    environment = os.getenv("SENTRY_ENVIRONMENT", "streamlit-cloud")
    traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2"))

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
    )
    return True