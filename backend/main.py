from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import time

from backend.config import CORS_ORIGINS
from backend.db import Base, engine, init_db
from backend.routers import api
from backend.routers import live as live_router

# Create tables and run lightweight migrations
init_db(engine)

app = FastAPI(title="Honeypot ML Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(live_router.router)
app.include_router(api.router)


# ---------------------------------------------------------------------------
# Extended /health – include ingest running status
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    from backend.db import engine as _engine, SessionLocal
    from backend.models import IngestStatus
    from backend.services.model_service import model_service

    try:
        with _engine.connect() as _:
            pass
        db_ok = True
    except Exception:
        db_ok = False

    ingest_running = False
    last_session_age_sec = None
    now = time.time()

    db = SessionLocal()
    try:
        row = db.query(IngestStatus).filter(IngestStatus.id == 1).first()
        if row and row.heartbeat_at:
            ingest_running = (now - row.heartbeat_at) < 90
            if row.last_session_time:
                last_session_age_sec = round(now - row.last_session_time, 1)
    except Exception:
        pass
    finally:
        db.close()

    return {
        "status": "ok" if db_ok else "degraded",
        "db_ok": db_ok,
        "model_loaded": model_service.model_loaded,
        "model_mode": model_service.model_mode,
        "model_version": model_service.model_version,
        "ingest_running": ingest_running,
        "last_session_age_sec": last_session_age_sec,
    }
