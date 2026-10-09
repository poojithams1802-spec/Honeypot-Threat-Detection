"""
tests/test_ingest.py
====================
Integration tests for Phase 6 ingest pipeline.

Coverage
--------
1. Tailer: appended lines
2. Tailer: partial lines
3. Tailer: malformed JSON lines (skip + count)
4. Tailer: truncation (size shrink)
5. Tailer: rotation (inode change / new file)
6. SessionTracker: finalize on closed event
7. SessionTracker: finalize on idle timeout, marks session_incomplete=1
8. SessionTracker: memory cap evicts oldest as incomplete
9. Idempotent inserts (run ingestor twice, row count unchanged)
10. Checkpoint resume (stop mid-file, restart, no duplicates, no losses)
11. Model-missing path stores NULL predictions (needs_rescore=True)
12. SSE endpoint emits a newly inserted row
"""

import json
import os
import tempfile
import threading
import time
import shutil
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# We use an in-memory SQLite DB for all ingest tests
# ---------------------------------------------------------------------------

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_cowrie.json"
)


@pytest.fixture
def tmp_db():
    """Provide a fresh SQLite DB and override DATABASE_URL for the process."""
    db_path = tempfile.mktemp(suffix=".db")
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url

    import sys
    import backend.config
    backend.config.DATABASE_URL = url
    import backend.db
    backend.db.DATABASE_URL = url
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    eng = create_engine(url, connect_args={"check_same_thread": False})
    backend.db.engine = eng
    backend.db.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=eng)

    if "backend.ingest.run_ingest" in sys.modules:
        sys.modules["backend.ingest.run_ingest"].engine = eng
        sys.modules["backend.ingest.run_ingest"].SessionLocal = backend.db.SessionLocal

    from backend.db import Base
    Base.metadata.create_all(bind=eng)

    yield url

    # Teardown
    eng.dispose()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def tmp_log():
    """Provide a fresh empty temp log file and return its path."""
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    fh.close()
    yield fh.name
    try:
        os.unlink(fh.name)
    except OSError:
        pass


# ===========================================================================
# 1. Tailer: appended lines
# ===========================================================================

def test_tailer_appended_lines(tmp_log):
    from backend.ingest.tailer import LogTailer

    events_received = []
    stop = threading.Event()

    tailer = LogTailer(tmp_log)

    def writer():
        time.sleep(0.1)
        with open(tmp_log, "a", encoding="utf-8") as f:
            f.write('{"eventid":"cowrie.session.connect","session":"t1","timestamp":"2023-01-01T00:00:00Z","src_ip":"1.1.1.1","dst_port":2222}\n')
            f.flush()
        time.sleep(0.2)
        stop.set()

    t = threading.Thread(target=writer, daemon=True)
    t.start()

    for ev, _ in tailer.follow(stop_event=stop):
        events_received.append(ev)

    t.join(timeout=3)
    assert len(events_received) == 1
    assert events_received[0]["session"] == "t1"


# ===========================================================================
# 2. Tailer: partial lines
# ===========================================================================

def test_tailer_partial_lines(tmp_log):
    from backend.ingest.tailer import LogTailer

    stop = threading.Event()
    received = []
    tailer = LogTailer(tmp_log)

    def writer():
        with open(tmp_log, "ab") as f:
            # Write first half of a JSON line, no newline
            partial = b'{"eventid":"cowrie.session.connect","session":"p1",'
            f.write(partial)
            f.flush()
        time.sleep(0.15)
        with open(tmp_log, "ab") as f:
            # Complete the line
            rest = b'"timestamp":"2023-01-01T00:00:00Z","src_ip":"9.9.9.9","dst_port":2222}\n'
            f.write(rest)
            f.flush()
        time.sleep(0.2)
        stop.set()

    t = threading.Thread(target=writer, daemon=True)
    t.start()

    for ev, _ in tailer.follow(stop_event=stop):
        received.append(ev)

    t.join(timeout=3)
    assert len(received) == 1
    assert received[0]["session"] == "p1"


# ===========================================================================
# 3. Tailer: malformed JSON (skip + count)
# ===========================================================================

def test_tailer_malformed_json(tmp_log):
    from backend.ingest.tailer import LogTailer

    stop = threading.Event()
    received = []
    tailer = LogTailer(tmp_log)

    def writer():
        with open(tmp_log, "a", encoding="utf-8") as f:
            f.write("NOT JSON AT ALL\n")
            f.write('{"eventid":"cowrie.session.connect","session":"m1","timestamp":"2023-01-01T00:00:00Z","src_ip":"1.1.1.1","dst_port":2222}\n')
            f.write("{broken json\n")
            f.flush()
        time.sleep(0.2)
        stop.set()

    t = threading.Thread(target=writer, daemon=True)
    t.start()

    for ev, _ in tailer.follow(stop_event=stop):
        received.append(ev)

    t.join(timeout=3)
    assert len(received) == 1
    assert tailer.malformed_lines == 2


# ===========================================================================
# 4. Tailer: truncation
# ===========================================================================

def test_tailer_truncation(tmp_log):
    from backend.ingest.tailer import LogTailer

    stop = threading.Event()
    received = []
    tailer = LogTailer(tmp_log)

    def writer():
        try:
            with open(tmp_log, "a", encoding="utf-8") as f:
                # Write multiple lines so initial size is larger than truncated size
                f.write('{"eventid":"cowrie.session.connect","session":"tr1","timestamp":"2023-01-01T00:00:00Z","src_ip":"1.1.1.1","dst_port":2222}\n')
                f.write('{"eventid":"cowrie.session.connect","session":"tr1_extra","timestamp":"2023-01-01T00:00:01Z","src_ip":"1.1.1.1","dst_port":2222}\n')
                f.flush()
            time.sleep(0.15)
            # Truncate the file (shorter single line so stat.st_size < offset triggers)
            with open(tmp_log, "w", encoding="utf-8") as f:
                f.write('{"eventid":"cowrie.session.connect","session":"tr2","timestamp":"2023-01-01T00:01:00Z","src_ip":"2.2.2.2","dst_port":2222}\n')
                f.flush()
            time.sleep(0.3)
        finally:
            stop.set()

    t = threading.Thread(target=writer, daemon=True)
    t.start()

    for ev, _ in tailer.follow(stop_event=stop):
        received.append(ev)

    t.join(timeout=4)
    sessions = [e["session"] for e in received]
    assert "tr1" in sessions
    assert "tr2" in sessions


# ===========================================================================
# 5. Tailer: rotation (new file at same path)
# ===========================================================================

def test_tailer_rotation(tmp_log):
    from backend.ingest.tailer import LogTailer

    stop = threading.Event()
    received = []
    tailer = LogTailer(tmp_log)
    rotated_path = tmp_log + ".rotated"

    def writer():
        try:
            with open(tmp_log, "a", encoding="utf-8") as f:
                f.write('{"eventid":"cowrie.session.connect","session":"rot1","timestamp":"2023-01-01T00:00:00Z","src_ip":"1.1.1.1","dst_port":2222}\n')
                f.flush()
            time.sleep(0.15)
            # Simulate rotation: rename old file and create new file at same path
            try:
                os.rename(tmp_log, rotated_path)
            except OSError:
                os.unlink(tmp_log)
            time.sleep(0.05)
            with open(tmp_log, "w", encoding="utf-8") as f:
                f.write('{"eventid":"cowrie.session.connect","session":"rot2","timestamp":"2023-01-01T00:01:00Z","src_ip":"3.3.3.3","dst_port":2222}\n')
                f.flush()
            time.sleep(0.3)
        finally:
            stop.set()

    t = threading.Thread(target=writer, daemon=True)
    t.start()

    for ev, _ in tailer.follow(stop_event=stop):
        received.append(ev)

    t.join(timeout=4)
    sessions = [e["session"] for e in received]
    assert "rot1" in sessions
    assert "rot2" in sessions

    try:
        if os.path.exists(rotated_path):
            os.unlink(rotated_path)
    except OSError:
        pass


# ===========================================================================
# 6. SessionTracker: finalize on closed
# ===========================================================================

def test_tracker_finalize_on_closed():
    from ml.parse_logs import parse_iso8601
    from ml.features import IPContextTracker
    from backend.ingest.session_tracker import SessionTracker

    finalized = []

    def on_fin(feat):
        finalized.append(feat)

    tracker = SessionTracker(on_finalized=on_fin, ip_tracker=IPContextTracker())

    events = [
        {"eventid": "cowrie.session.connect", "session": "c1",
         "timestamp": "2023-01-01T10:00:00Z", "src_ip": "1.1.1.1", "dst_port": 2222},
        {"eventid": "cowrie.login.failed", "session": "c1",
         "timestamp": "2023-01-01T10:00:02Z", "username": "root", "password": "1234"},
        {"eventid": "cowrie.session.closed", "session": "c1",
         "timestamp": "2023-01-01T10:00:05Z"},
    ]
    for e in events:
        e["timestamp_sec"] = parse_iso8601(e["timestamp"])
        tracker.ingest_event(e)

    assert len(finalized) == 1
    assert finalized[0]["session_id"] == "c1"
    assert finalized[0]["session_incomplete"] == 0
    assert finalized[0]["n_login_failed"] == 1


# ===========================================================================
# 7. SessionTracker: idle timeout marks session_incomplete
# ===========================================================================

def test_tracker_idle_timeout():
    from ml.parse_logs import parse_iso8601
    from ml.features import IPContextTracker
    from backend.ingest.session_tracker import SessionTracker

    finalized = []

    def on_fin(feat):
        finalized.append(feat)

    tracker = SessionTracker(on_finalized=on_fin, ip_tracker=IPContextTracker())

    events = [
        {"eventid": "cowrie.session.connect", "session": "idle1",
         "timestamp": "2023-01-01T10:00:00Z", "src_ip": "2.2.2.2", "dst_port": 2222},
    ]
    for e in events:
        e["timestamp_sec"] = parse_iso8601(e["timestamp"])
        tracker.ingest_event(e)

    assert len(finalized) == 0  # not finalized yet

    # Simulate idle timeout by passing a far-future `now`
    flushed = tracker.flush_idle(now=float("inf"))

    assert flushed == 1
    assert len(finalized) == 1
    assert finalized[0]["session_incomplete"] == 1


# ===========================================================================
# 8. SessionTracker: memory cap evicts oldest
# ===========================================================================

def test_tracker_memory_cap():
    import os
    import importlib

    # Temporarily set a tiny cap
    os.environ["MAX_ACTIVE_SESSIONS"] = "2"
    import backend.ingest.session_tracker as st_mod
    importlib.reload(st_mod)

    finalized = []

    def on_fin(feat):
        finalized.append(feat)

    from ml.features import IPContextTracker
    from ml.parse_logs import parse_iso8601

    tracker = st_mod.SessionTracker(
        on_finalized=on_fin,
        ip_tracker=IPContextTracker(),
    )

    # Add 3 sessions – third one should evict the first
    for i in range(1, 4):
        e = {
            "eventid": "cowrie.session.connect",
            "session": f"cap{i}",
            "timestamp": f"2023-01-01T10:0{i}:00Z",
            "src_ip": f"{i}.{i}.{i}.{i}",
            "dst_port": 2222,
        }
        e["timestamp_sec"] = parse_iso8601(e["timestamp"])
        tracker.ingest_event(e)

    # cap1 should have been evicted as incomplete
    assert any(f["session_id"] == "cap1" and f["session_incomplete"] == 1
               for f in finalized), f"cap1 not evicted. finalized={[f['session_id'] for f in finalized]}"

    # Restore
    os.environ.pop("MAX_ACTIVE_SESSIONS", None)
    importlib.reload(st_mod)


# ===========================================================================
# 9. Idempotent inserts
# ===========================================================================

def test_idempotent_inserts(tmp_db, tmp_log):
    """Run replay ingestor twice; row count must be identical after second run."""
    # Write a simple log
    with open(tmp_log, "w", encoding="utf-8") as f:
        f.write('{"eventid":"cowrie.session.connect","session":"idem1","timestamp":"2023-01-01T10:00:00Z","src_ip":"5.5.5.5","dst_port":2222}\n')
        f.write('{"eventid":"cowrie.session.closed","session":"idem1","timestamp":"2023-01-01T10:00:05Z"}\n')

    def _run_replay():
        from backend.ingest.run_ingest import ReplayIngestor
        r = ReplayIngestor(log_path=tmp_log, state_file=tmp_log + ".state", replay_speed=0)
        r.run()

    _run_replay()

    from backend.db import SessionLocal
    from backend.models import SessionRecord
    db = SessionLocal()
    count1 = db.query(SessionRecord).count()
    db.close()

    _run_replay()

    db = SessionLocal()
    count2 = db.query(SessionRecord).count()
    db.close()

    assert count1 == count2 == 1, f"Expected 1 row after both runs; got {count1} then {count2}"


# ===========================================================================
# 10. Checkpoint resume
# ===========================================================================

def test_checkpoint_resume(tmp_db):
    """Stop mid-file, restart with checkpoint, verify no duplicates or losses."""
    import tempfile
    from backend.ingest.run_ingest import ReplayIngestor

    tmp_log = tempfile.mktemp(suffix=".json")
    state_file = tempfile.mktemp(suffix=".state.json")

    try:
        lines = []
        for i in range(1, 6):
            lines.append(
                f'{{"eventid":"cowrie.session.connect","session":"ck{i}",'
                f'"timestamp":"2023-01-01T10:0{i}:00Z","src_ip":"{i}.{i}.{i}.{i}","dst_port":2222}}\n'
            )
            lines.append(
                f'{{"eventid":"cowrie.session.closed","session":"ck{i}",'
                f'"timestamp":"2023-01-01T10:0{i}:05Z"}}\n'
            )

        # Write first 3 sessions
        with open(tmp_log, "w", encoding="utf-8") as f:
            f.writelines(lines[:6])

        r1 = ReplayIngestor(log_path=tmp_log, state_file=state_file, replay_speed=0)
        r1.run()

        from backend.db import SessionLocal
        from backend.models import SessionRecord
        db = SessionLocal()
        c1 = db.query(SessionRecord).count()
        db.close()

        # Append remaining sessions
        with open(tmp_log, "a", encoding="utf-8") as f:
            f.writelines(lines[6:])

        # Second run from checkpoint – should only pick up new sessions
        r2 = ReplayIngestor(log_path=tmp_log, state_file=state_file, replay_speed=0)
        r2.run()

        db = SessionLocal()
        c2 = db.query(SessionRecord).count()
        db.close()

        assert c2 == 5, f"Expected 5 total sessions; got {c2}"
        assert c1 <= c2, "Second run should not delete rows"

    finally:
        for p in (tmp_log, state_file):
            try:
                os.unlink(p)
            except OSError:
                pass


# ===========================================================================
# 11. Model-missing path stores NULL predictions
# ===========================================================================

def test_null_prediction_when_model_missing(tmp_db):
    """When model is not loaded, session is stored with needs_rescore=True."""
    import importlib, backend.ingest.run_ingest as ri_mod
    importlib.reload(ri_mod)

    # Patch _MODEL_AVAILABLE to False
    orig = ri_mod._MODEL_AVAILABLE
    ri_mod._MODEL_AVAILABLE = False

    feat = {
        "session_id": "null_pred_test",
        "src_ip": "9.9.9.9",
        "start_time": 1672574400.0,
        "end_time": 1672574410.0,
        "duration_sec": 10.0,
        "protocol": 0,
        "has_client_version": 0,
        "n_login_failed": 0,
        "n_login_success": 0,
        "login_success_ratio": 0.0,
        "n_unique_usernames": 0,
        "n_unique_passwords": 0,
        "avg_secs_between_logins": 0.0,
        "n_commands": 0,
        "n_unique_commands": 0,
        "n_failed_commands": 0,
        "avg_secs_between_commands": 0.0,
        "avg_command_length": 0.0,
        "n_suspicious_commands": 0,
        "n_download_attempts": 0,
        "n_file_uploads": 0,
        "no_login_attempted": 1,
        "session_incomplete": 0,
        "ip_sessions_last_60s": 0,
        "ip_sessions_last_300s": 0,
        "ip_failed_logins_last_300s": 0,
        "ip_distinct_usernames_last_300s": 0,
        "_usernames": set(),
    }

    enriched = ri_mod._predict(feat)
    assert enriched["predicted_label"] is None
    assert enriched["needs_rescore"] is True

    from backend.db import SessionLocal
    from backend.models import SessionRecord

    db = SessionLocal()
    try:
        inserted = ri_mod._upsert_session(db, enriched, is_demo=False)
        assert inserted is True
        row = db.query(SessionRecord).filter(
            SessionRecord.session_id == "null_pred_test"
        ).first()
        assert row is not None
        assert row.predicted_label is None
        assert row.needs_rescore is True
    finally:
        db.close()
        ri_mod._MODEL_AVAILABLE = orig


# ===========================================================================
# 12. SSE endpoint emits newly inserted row
# ===========================================================================

def test_sse_emits_new_row(tmp_db):
    """The SSE generator must yield data for a row inserted after stream start."""
    import asyncio
    from backend.db import SessionLocal
    from backend.models import SessionRecord
    from backend.routers.live import _event_generator
    import time

    db = SessionLocal()
    try:
        # No rows initially
        gen = _event_generator(SessionLocal, include_demo=True)

        async def collect_first_data():
            # Fast-forward: insert a row after a brief delay, then collect
            async def insert_later():
                await asyncio.sleep(0.05)
                db2 = SessionLocal()
                try:
                    r = SessionRecord(
                        session_id="sse_test_1",
                        src_ip="1.2.3.4",
                        start_time=time.time(),
                        predicted_label="normal",
                        threat_level="Low",
                        confidence=0.9,
                        model_version="test",
                        model_mode="synthetic",
                        created_at=time.time(),
                        is_demo=False,
                    )
                    db2.add(r)
                    db2.commit()
                finally:
                    db2.close()

            asyncio.create_task(insert_later())

            data_events = []
            async for chunk in gen:
                if chunk.startswith("data:"):
                    data_events.append(chunk)
                    break  # got what we need
            return data_events

        loop = asyncio.new_event_loop()
        results = loop.run_until_complete(collect_first_data())
        loop.close()

        assert len(results) == 1
        payload = json.loads(results[0].replace("data: ", "").strip())
        assert payload["session_id"] == "sse_test_1"
    finally:
        db.close()
