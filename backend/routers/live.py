"""
backend/routers/live.py
=======================
Live-feed API endpoints for Phase 6.

Endpoints
---------
GET /events/stream          Server-Sent Events stream of new sessions
GET /ingest/status          Current ingestor health (reads ingest_status table)
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import IngestStatus, SessionRecord

logger = logging.getLogger(__name__)

router = APIRouter()

SSE_POLL_INTERVAL = 1.5    # seconds between DB polls in SSE stream
SSE_HEARTBEAT_INTERVAL = 15  # seconds between heartbeat comment lines
INGEST_RUNNING_THRESHOLD = 90  # seconds before ingestor is considered down


# ---------------------------------------------------------------------------
# Server-Sent Events stream
# ---------------------------------------------------------------------------

async def _event_generator(
    db_factory,
    include_demo: bool,
) -> AsyncGenerator[str, None]:
    """Async generator that polls the DB and yields SSE lines."""
    last_seen_id: int = 0

    # Initialise last_seen_id to the current max so we only emit NEW rows
    db: Session = db_factory()
    try:
        q = db.query(SessionRecord)
        if not include_demo:
            q = q.filter(SessionRecord.is_demo == False)  # noqa: E712
        latest = q.order_by(SessionRecord.id.desc()).first()
        if latest:
            last_seen_id = latest.id
    finally:
        db.close()

    last_heartbeat = time.monotonic()
    yield ": connected\n\n"

    while True:
        await asyncio.sleep(SSE_POLL_INTERVAL)

        # Heartbeat to keep the connection alive
        now = time.monotonic()
        if now - last_heartbeat >= SSE_HEARTBEAT_INTERVAL:
            yield ": heartbeat\n\n"
            last_heartbeat = now

        # Poll for new rows
        db = db_factory()
        try:
            q = db.query(SessionRecord).filter(SessionRecord.id > last_seen_id)
            if not include_demo:
                q = q.filter(SessionRecord.is_demo == False)  # noqa: E712
            rows = q.order_by(SessionRecord.id.asc()).all()
        finally:
            db.close()

        for row in rows:
            last_seen_id = row.id
            payload = {
                "id": row.id,
                "session_id": row.session_id,
                "src_ip": row.src_ip,
                "predicted_label": row.predicted_label,
                "threat_level": row.threat_level,
                "confidence": row.confidence,
                "start_time": row.start_time,
                "is_demo": row.is_demo,
            }
            data = json.dumps(payload)
            yield f"data: {data}\n\n"
            last_heartbeat = time.monotonic()


@router.get("/events/stream")
async def events_stream(
    include_demo: bool = Query(True, description="Include demo/replay rows"),
):
    """Server-Sent Events stream.

    Each event is a JSON object with:
        id, session_id, src_ip, predicted_label, threat_level, confidence,
        start_time, is_demo
    A heartbeat comment (`: heartbeat`) is sent every 15 s to keep the
    connection alive.
    """
    from backend.db import SessionLocal  # local import to avoid circular
    return StreamingResponse(
        _event_generator(SessionLocal, include_demo),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Ingest status
# ---------------------------------------------------------------------------

@router.get("/ingest/status")
def ingest_status(db: Session = Depends(get_db)):
    """Return ingestor health and statistics.

    Reads the ingest_status table written by the ingestor process every 30 s.
    The `running` field is True if the heartbeat is within 90 s.
    """
    row = db.query(IngestStatus).filter(IngestStatus.id == 1).first()
    now = time.time()

    if row is None:
        return {
            "running": False,
            "last_event_time": None,
            "last_session_time": None,
            "lines_read": 0,
            "malformed_lines": 0,
            "sessions_stored": 0,
            "lag_seconds": None,
            "heartbeat_at": None,
        }

    running = (
        row.heartbeat_at is not None
        and (now - row.heartbeat_at) < INGEST_RUNNING_THRESHOLD
    )

    lag = row.lag_seconds
    if row.last_event_time is not None and (now - row.last_event_time) > 86400:
        lag = None

    return {
        "running": running,
        "last_event_time": row.last_event_time,
        "last_session_time": row.last_session_time,
        "lines_read": row.lines_read,
        "malformed_lines": row.malformed_lines,
        "sessions_stored": row.sessions_stored,
        "lag_seconds": lag,
        "heartbeat_at": row.heartbeat_at,
    }
