"""
backend/ingest/run_ingest.py
============================
Live ingestion pipeline entry point.

Usage
-----
    python -m backend.ingest.run_ingest [options]

Options
-------
    --log PATH           Path to cowrie.json (default: COWRIE_LOG_PATH env or
                         data/cowrie_logs/cowrie.json)
    --from-start         Ignore checkpoint; read from byte 0 (idempotent inserts)
    --from-end           Start from current end of file; skip historical events
    --replay-speed X     Replay an existing log at X× real time (0 = max speed).
                         Replayed rows are stored with is_demo=True.
    --state-file PATH    Path to checkpoint JSON (default: data/ingest_state.json)

Environment Variables
---------------------
    COWRIE_LOG_PATH          Path to cowrie.json
    SESSION_IDLE_TIMEOUT_SEC  Seconds of inactivity before a session is finalised as
                              incomplete (default: 120)
    MAX_ACTIVE_SESSIONS       Memory cap for active sessions (default: 5000)
    DATABASE_URL              SQLAlchemy URL (default: sqlite:///./data/dev.db)
    MODEL_MODE                auto | real | synthetic (default: auto)
"""

import argparse
import json
import logging
import os
import shutil
import signal
import sys
import tempfile
import threading
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Setup logging before any imports that might log
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ingest")

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
from backend.db import SessionLocal, Base, engine
from backend.ingest.tailer import LogTailer
from backend.ingest.session_tracker import SessionTracker, IP_HISTORY_WINDOW_SEC
from backend.models import SessionRecord, IngestStatus
from ml.features import IPContextTracker, extract_session_features
from ml.parse_logs import parse_iso8601

# Ensure tables exist
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Model service (optional – store NULLs if not loaded)
# ---------------------------------------------------------------------------
try:
    from backend.services.model_service import model_service
    _MODEL_AVAILABLE = model_service.model_loaded
except Exception as _e:
    logger.warning("Model service unavailable: %s – predictions will be NULL.", _e)
    model_service = None
    _MODEL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_LOG_PATH = os.getenv(
    "COWRIE_LOG_PATH",
    os.path.join("data", "cowrie_logs", "cowrie.json"),
)
DEFAULT_STATE_FILE = os.path.join("data", "ingest_state.json")
STATUS_INTERVAL = 30  # seconds between structured-log prints
HEARTBEAT_INTERVAL = 30  # seconds between DB status updates


# ===========================================================================
# Checkpoint helpers
# ===========================================================================

def _load_checkpoint(state_file: str) -> dict:
    try:
        with open(state_file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_checkpoint(state_file: str, offset: int, inode: Optional[int]) -> None:
    """Atomic write: write to tmp then rename."""
    data = {"offset": offset, "inode": inode, "ts": time.time()}
    tmp = state_file + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f)
        shutil.move(tmp, state_file)
    except OSError as e:
        logger.error("Failed to save checkpoint: %s", e)


# ===========================================================================
# DB helpers
# ===========================================================================

def _upsert_session(db, feat: dict, is_demo: bool) -> bool:
    """Insert a session record; skip if session_id already exists.

    Returns True if inserted, False if skipped.
    """
    existing = (
        db.query(SessionRecord)
        .filter(SessionRecord.session_id == feat["session_id"])
        .first()
    )
    if existing:
        return False

    pred_label = feat.get("predicted_label")
    probabilities = feat.get("probabilities")
    confidence = feat.get("confidence")
    threat_level = feat.get("threat_level")
    anomaly_score = feat.get("anomaly_score")
    is_anomalous = feat.get("is_anomalous")
    model_version = feat.get("model_version")
    model_mode = feat.get("model_mode")
    needs_rescore = feat.get("needs_rescore", False)

    # Build the feature dict (only FEATURE_COLUMNS, no metadata)
    from ml.config import FEATURE_COLUMNS
    features_dict = {k: feat.get(k) for k in FEATURE_COLUMNS}

    record = SessionRecord(
        session_id=feat["session_id"],
        src_ip=feat.get("src_ip", "0.0.0.0"),
        dst_port=feat.get("dst_port"),
        protocol=feat.get("protocol"),
        start_time=feat["start_time"],
        end_time=feat.get("end_time"),
        duration_sec=feat.get("duration_sec"),
        n_login_failed=feat.get("n_login_failed"),
        n_login_success=feat.get("n_login_success"),
        n_commands=feat.get("n_commands"),
        usernames=list(feat.get("_usernames", []))[:20] or None,
        passwords=list(feat.get("_passwords", []))[:20] or None,
        commands=list(feat.get("_commands", []))[:50] or None,
        features=features_dict,
        predicted_label=pred_label,
        probabilities=probabilities,
        confidence=confidence,
        threat_level=threat_level,
        anomaly_score=anomaly_score,
        is_anomalous=is_anomalous,
        model_version=model_version,
        model_mode=model_mode,
        created_at=time.time(),
        is_demo=is_demo,
        needs_rescore=needs_rescore,
    )
    db.add(record)
    db.commit()
    return True


def _predict(feat: dict) -> dict:
    """Run ML prediction; return enriched feat dict. Falls back to NULLs."""
    if not _MODEL_AVAILABLE:
        feat["predicted_label"] = None
        feat["probabilities"] = None
        feat["confidence"] = None
        feat["threat_level"] = None
        feat["anomaly_score"] = None
        feat["is_anomalous"] = None
        feat["model_version"] = None
        feat["model_mode"] = None
        feat["needs_rescore"] = True
        return feat

    from ml.config import FEATURE_COLUMNS
    feat_dict = {k: feat.get(k, 0.0) for k in FEATURE_COLUMNS}
    try:
        result = model_service.predict_single(feat_dict)
        feat["predicted_label"] = result["predicted_label"]
        feat["probabilities"] = result["class_probabilities"]
        feat["confidence"] = result["confidence"]
        feat["threat_level"] = result["threat_level"]
        feat["anomaly_score"] = result["anomaly_score"]
        feat["is_anomalous"] = result["is_anomalous"]
        feat["model_version"] = model_service.model_version
        feat["model_mode"] = model_service.model_mode
        feat["needs_rescore"] = False
    except Exception as exc:
        logger.error("Prediction error for %s: %s", feat.get("session_id"), exc)
        feat["predicted_label"] = None
        feat["probabilities"] = None
        feat["confidence"] = None
        feat["threat_level"] = None
        feat["anomaly_score"] = None
        feat["is_anomalous"] = None
        feat["model_version"] = None
        feat["model_mode"] = None
        feat["needs_rescore"] = True
    return feat


# ===========================================================================
# Stats counters (shared between threads via GIL – simple enough)
# ===========================================================================

class _Stats:
    def __init__(self):
        self.lines_read = 0
        self.malformed_lines = 0
        self.sessions_finalized = 0
        self.predictions_stored = 0
        self.predictions_skipped = 0
        self.errors = 0
        self.last_event_ts: Optional[float] = None
        self.last_session_ts: Optional[float] = None
        self._t0 = time.time()

    def print_summary(self):
        lag = (time.time() - self.last_event_ts) if self.last_event_ts else None
        logger.info(
            "STATS | lines_read=%d malformed=%d sessions=%d stored=%d "
            "skipped=%d errors=%d lag=%.1fs",
            self.lines_read,
            self.malformed_lines,
            self.sessions_finalized,
            self.predictions_stored,
            self.predictions_skipped,
            self.errors,
            lag if lag is not None else -1,
        )


# ===========================================================================
# Main ingestor
# ===========================================================================

class Ingestor:
    """Orchestrates tailing, tracking, predicting, and storing sessions."""

    def __init__(
        self,
        log_path: str,
        state_file: str,
        from_start: bool = False,
        from_end: bool = False,
        is_demo: bool = False,
    ):
        self.log_path = log_path
        self.state_file = state_file
        self.is_demo = is_demo
        self._stop = threading.Event()
        self._stats = _Stats()

        # Load checkpoint
        ckpt = _load_checkpoint(state_file)
        if from_start:
            offset, inode = 0, None
        elif from_end:
            offset = os.path.getsize(log_path) if os.path.exists(log_path) else 0
            inode = None
        else:
            offset = ckpt.get("offset", 0)
            inode = ckpt.get("inode")

        self._tailer = LogTailer(log_path, start_offset=offset, start_inode=inode)

        # Build IP tracker and warm from DB
        self._ip_tracker = IPContextTracker(max_sessions_per_ip=200)
        self._warm_ip_tracker()

        # Session tracker
        self._tracker = SessionTracker(
            on_finalized=self._on_session_finalized,
            ip_tracker=self._ip_tracker,
            is_demo=is_demo,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        logger.info("Ingestor starting. log=%s is_demo=%s", self.log_path, self.is_demo)

        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle_signal)
            except (OSError, ValueError):
                pass  # Windows may not support all signals

        last_status_print = time.time()
        last_checkpoint = time.time()
        last_idle_flush = time.time()
        last_heartbeat = time.time()

        for event, _raw in self._tailer.follow(stop_event=self._stop):
            if self._stop.is_set():
                break

            self._stats.lines_read += 1
            ts = event.get("timestamp_sec") or parse_iso8601(event.get("timestamp", ""))
            if ts:
                self._stats.last_event_ts = ts

            self._tracker.ingest_event(event)

            now = time.time()

            # Flush idle sessions periodically
            if now - last_idle_flush >= 10:
                flushed = self._tracker.flush_idle(now=now)
                if flushed:
                    logger.debug("Idle flush: %d sessions", flushed)
                last_idle_flush = now

            # Checkpoint periodically
            if now - last_checkpoint >= 5:
                _save_checkpoint(
                    self.state_file,
                    self._tailer.offset,
                    self._tailer.inode,
                )
                last_checkpoint = now

            # Structured log print
            if now - last_status_print >= STATUS_INTERVAL:
                self._stats.malformed_lines = self._tailer.malformed_lines
                self._stats.print_summary()
                last_status_print = now

            # DB heartbeat for /ingest/status
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                self._write_ingest_status()
                last_heartbeat = now

        self._shutdown()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_session_finalized(self, feat: dict) -> None:
        self._stats.sessions_finalized += 1
        self._stats.last_session_ts = time.time()

        meta = self._tracker.pop_session_metadata(feat.get("session_id", ""))
        if meta:
            feat["_usernames"] = meta.get("usernames", [])
            feat["_passwords"] = meta.get("passwords", [])
            feat["_commands"] = meta.get("commands", [])

        # Predict
        feat = _predict(feat)

        # Store
        db = SessionLocal()
        try:
            inserted = _upsert_session(db, feat, self.is_demo)
            if inserted:
                self._stats.predictions_stored += 1
            else:
                self._stats.predictions_skipped += 1
        except Exception as exc:
            logger.error("DB insert error: %s", exc)
            self._stats.errors += 1
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _warm_ip_tracker(self) -> None:
        """Seed IP tracker from sessions in the last IP_HISTORY_WINDOW_SEC."""
        cutoff = time.time() - IP_HISTORY_WINDOW_SEC
        db = SessionLocal()
        try:
            rows = (
                db.query(SessionRecord)
                .filter(
                    SessionRecord.start_time >= cutoff,
                    SessionRecord.is_demo == self.is_demo,
                )
                .order_by(SessionRecord.start_time)
                .all()
            )
            sessions = [
                {
                    "src_ip": r.src_ip,
                    "start_time": r.start_time,
                    "n_login_failed": r.n_login_failed or 0,
                    "usernames": r.usernames or [],
                }
                for r in rows
            ]
            self._ip_tracker.seed_from_sessions(sessions)
            logger.info("Warmed IP tracker from %d DB sessions.", len(sessions))
        except Exception as e:
            logger.warning("Could not warm IP tracker from DB: %s", e)
        finally:
            db.close()

    def _write_ingest_status(self) -> None:
        """Persist ingest heartbeat to the ingest_status table."""
        db = SessionLocal()
        try:
            s = db.query(IngestStatus).filter(IngestStatus.id == 1).first()
            now = time.time()
            lag = (now - self._stats.last_event_ts) if self._stats.last_event_ts else None
            if s is None:
                s = IngestStatus(id=1)
                db.add(s)
            s.last_event_time = self._stats.last_event_ts
            s.last_session_time = self._stats.last_session_ts
            s.lines_read = self._stats.lines_read
            s.malformed_lines = self._tailer.malformed_lines
            s.sessions_stored = self._stats.predictions_stored
            s.heartbeat_at = now
            s.lag_seconds = lag
            db.commit()
        except Exception as e:
            logger.warning("Could not write ingest status: %s", e)
        finally:
            db.close()

    def _handle_signal(self, signum, frame) -> None:
        logger.info("Received signal %d; initiating graceful shutdown.", signum)
        self._stop.set()

    def _shutdown(self) -> None:
        logger.info("Shutting down; flushing remaining sessions...")
        flushed = self._tracker.flush_all()
        logger.info("Flushed %d remaining sessions.", flushed)
        _save_checkpoint(self.state_file, self._tailer.offset, self._tailer.inode)
        self._write_ingest_status()
        self._stats.malformed_lines = self._tailer.malformed_lines
        self._stats.print_summary()
        logger.info("Ingestor stopped.")


# ===========================================================================
# Replay mode
# ===========================================================================

class ReplayIngestor:
    """Read an existing log and feed events at replay_speed × real-time.

    replay_speed=0 means as fast as possible.
    All stored rows are marked is_demo=True.
    """

    def __init__(
        self,
        log_path: str,
        state_file: str,
        replay_speed: float = 0.0,
    ):
        self.log_path = log_path
        self.state_file = state_file
        self.replay_speed = replay_speed
        self._stats = _Stats()
        self._stop = threading.Event()

        self._ip_tracker = IPContextTracker(max_sessions_per_ip=200)
        self._warm_ip_tracker()
        self._tracker = SessionTracker(
            on_finalized=self._on_session_finalized,
            ip_tracker=self._ip_tracker,
            is_demo=True,
        )

    def run(self) -> None:
        logger.info(
            "Replay starting. log=%s speed=%.1fx", self.log_path, self.replay_speed
        )
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle_signal)
            except (OSError, ValueError):
                pass

        tailer = LogTailer(self.log_path)
        prev_ts: Optional[float] = None
        real_prev = time.time()

        for event, _raw in tailer.read_from_start():
            if self._stop.is_set():
                break

            self._stats.lines_read += 1
            ev_ts = parse_iso8601(event.get("timestamp", ""))
            event["timestamp_sec"] = ev_ts

            if self.replay_speed > 0 and prev_ts is not None and ev_ts > prev_ts:
                sim_gap = (ev_ts - prev_ts) / self.replay_speed
                real_elapsed = time.time() - real_prev
                sleep_for = sim_gap - real_elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)

            prev_ts = ev_ts
            real_prev = time.time()

            self._stats.last_event_ts = ev_ts
            self._tracker.ingest_event(event)

        # Flush all remaining sessions (they're "incomplete" in replay)
        self._tracker.flush_all(now=time.time() + 1e9)
        self._stats.malformed_lines = tailer.malformed_lines
        self._write_ingest_status()
        self._stats.print_summary()
        logger.info("Replay complete.")

    def _write_ingest_status(self) -> None:
        """Persist ingest heartbeat to the ingest_status table."""
        db = SessionLocal()
        try:
            s = db.query(IngestStatus).filter(IngestStatus.id == 1).first()
            now = time.time()
            lag = (now - self._stats.last_event_ts) if self._stats.last_event_ts else None
            if s is None:
                s = IngestStatus(id=1)
                db.add(s)
            s.last_event_time = self._stats.last_event_ts
            s.last_session_time = self._stats.last_session_ts
            s.lines_read = self._stats.lines_read
            s.malformed_lines = self._stats.malformed_lines
            s.sessions_stored = db.query(SessionRecord).count()
            s.heartbeat_at = now
            s.lag_seconds = lag
            db.commit()
        except Exception as e:
            logger.warning("Could not write ingest status: %s", e)
        finally:
            db.close()

    def _on_session_finalized(self, feat: dict) -> None:
        self._stats.sessions_finalized += 1
        self._stats.last_session_ts = feat.get("end_time") or feat.get("start_time")
        meta = self._tracker.pop_session_metadata(feat.get("session_id", ""))
        if meta:
            feat["_usernames"] = meta.get("usernames", [])
            feat["_passwords"] = meta.get("passwords", [])
            feat["_commands"] = meta.get("commands", [])
        feat = _predict(feat)
        db = SessionLocal()
        try:
            inserted = _upsert_session(db, feat, is_demo=True)
            if inserted:
                self._stats.predictions_stored += 1
            else:
                self._stats.predictions_skipped += 1
        except Exception as exc:
            logger.error("DB insert error: %s", exc)
            self._stats.errors += 1
        finally:
            db.close()

    def _warm_ip_tracker(self) -> None:
        pass  # replay always starts fresh

    def _handle_signal(self, signum, frame) -> None:
        logger.info("Replay: signal %d; stopping.", signum)
        self._stop.set()


# ===========================================================================
# CLI entry point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Honeypot-ML live ingestion pipeline"
    )
    parser.add_argument(
        "--log",
        default=DEFAULT_LOG_PATH,
        help="Path to cowrie.json (default: COWRIE_LOG_PATH env or data/cowrie_logs/cowrie.json)",
    )
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help="Path for checkpoint JSON (default: data/ingest_state.json)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--from-start",
        action="store_true",
        help="Ignore checkpoint; read from byte 0 (idempotent inserts guard duplicates)",
    )
    group.add_argument(
        "--from-end",
        action="store_true",
        help="Start from current EOF; only process future events",
    )
    parser.add_argument(
        "--replay-speed",
        type=float,
        default=None,
        metavar="X",
        help="Replay speed multiplier (0=max, >0=X× real time). Enables replay mode.",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.state_file), exist_ok=True)

    if args.replay_speed is not None:
        ingestor = ReplayIngestor(
            log_path=args.log,
            state_file=args.state_file,
            replay_speed=args.replay_speed,
        )
    else:
        ingestor = Ingestor(
            log_path=args.log,
            state_file=args.state_file,
            from_start=args.from_start,
            from_end=args.from_end,
            is_demo=False,
        )

    ingestor.run()


if __name__ == "__main__":
    main()
