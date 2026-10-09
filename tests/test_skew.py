"""
tests/test_skew.py
==================
No training/serving skew test.

Runs the BATCH pipeline (ml.build_dataset path: read_and_group_events +
extract_all_features) and the LIVE pipeline (event-by-event ingestion via
SessionTracker) on the SAME fixture log file, then asserts that every feature
value is identical (within float tolerance).

A failure here means the live and batch pipelines diverge – which would
invalidate model predictions in production.
"""

import math
import os
import pytest
from collections import defaultdict

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_cowrie.json"
)

FLOAT_TOL = 1e-9  # tolerance for float comparison


# ---------------------------------------------------------------------------
# Batch pipeline
# ---------------------------------------------------------------------------

def run_batch_pipeline(log_path: str) -> dict:
    """Run the batch pipeline and return {session_id: feature_dict}."""
    from ml.parse_logs import read_and_group_events
    from ml.features import extract_all_features

    sessions_dict, _, _ = read_and_group_events(log_path)
    features_list = extract_all_features(sessions_dict)
    return {f["session_id"]: f for f in features_list}


# ---------------------------------------------------------------------------
# Live pipeline (event-by-event, exactly as the ingestor does it)
# ---------------------------------------------------------------------------

def run_live_pipeline(log_path: str) -> dict:
    """Simulate the live pipeline on the fixture file.

    Reads events one by one (as if they streamed in), feeds them into
    SessionTracker, and collects finalised sessions.

    Returns {session_id: feature_dict}.
    """
    from ml.parse_logs import parse_iso8601
    from ml.features import IPContextTracker
    from backend.ingest.session_tracker import SessionTracker

    results = {}

    def on_finalized(feat: dict) -> None:
        # Make a copy; strip the temporary _usernames field (batch also strips it)
        f = {k: v for k, v in feat.items() if k not in ("_usernames", "is_demo")}
        results[f["session_id"]] = f

    ip_tracker = IPContextTracker()
    tracker = SessionTracker(
        on_finalized=on_finalized,
        ip_tracker=ip_tracker,
        is_demo=False,
    )

    import json
    with open(log_path, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue  # malformed – skip exactly as the tailer does

            ts_str = event.get("timestamp", "")
            event["timestamp_sec"] = parse_iso8601(ts_str)
            tracker.ingest_event(event)

    # Flush everything (simulate session closed or idle timeout at end of stream)
    # Use a far-future "now" so all sessions are considered idle
    tracker.flush_all(now=float("inf"))

    return results


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("session_id", [
    "s1", "s2", "s3", "s4", "s6", "s7", "s8", "s9", "s10", "s11",
])
def test_no_skew_per_session(session_id):
    """Each finalised session must have identical features in both pipelines."""
    batch = run_batch_pipeline(FIXTURE)
    live = run_live_pipeline(FIXTURE)

    assert session_id in batch, f"Batch pipeline missing session {session_id}"
    assert session_id in live,  f"Live pipeline missing session {session_id}"

    b = batch[session_id]
    lv = live[session_id]

    # Collect differences
    diffs = []
    all_keys = set(b.keys()) | set(lv.keys())
    skip_keys = {"session_id", "src_ip", "_usernames", "is_demo"}

    for key in sorted(all_keys):
        if key in skip_keys:
            continue
        bv = b.get(key)
        lv_v = lv.get(key)

        if isinstance(bv, float) and isinstance(lv_v, float):
            if not (math.isnan(bv) and math.isnan(lv_v)):
                if abs(bv - lv_v) > FLOAT_TOL:
                    diffs.append(
                        f"  {key}: batch={bv!r}  live={lv_v!r}  diff={abs(bv - lv_v):.2e}"
                    )
        elif bv != lv_v:
            diffs.append(f"  {key}: batch={bv!r}  live={lv_v!r}")

    assert not diffs, (
        f"SKEW DETECTED in session {session_id}:\n" + "\n".join(diffs)
    )


def test_no_skew_full_dataset():
    """All sessions in batch output must be present and equal in live output."""
    batch = run_batch_pipeline(FIXTURE)
    live = run_live_pipeline(FIXTURE)

    batch_ids = set(batch.keys())
    live_ids = set(live.keys())

    # s5 has no closed event and is only seen by live if idle-flushed;
    # batch always includes it. This is expected behaviour.
    # We assert the sets are equal (both pipelines include the same sessions).
    missing_in_live = batch_ids - live_ids
    extra_in_live = live_ids - batch_ids

    assert not missing_in_live, f"Sessions in batch but not live: {missing_in_live}"
    assert not extra_in_live, f"Sessions in live but not batch: {extra_in_live}"

    # Check all features for all sessions
    all_diffs = []
    skip_keys = {"session_id", "src_ip", "_usernames", "is_demo"}

    for sid in sorted(batch_ids):
        b = batch[sid]
        lv = live[sid]
        for key in sorted(set(b.keys()) | set(lv.keys())):
            if key in skip_keys:
                continue
            bv = b.get(key)
            lv_v = lv.get(key)
            if isinstance(bv, float) and isinstance(lv_v, float):
                if not (math.isnan(bv) and math.isnan(lv_v)):
                    if abs(bv - lv_v) > FLOAT_TOL:
                        all_diffs.append(
                            f"  [{sid}] {key}: batch={bv!r} live={lv_v!r}"
                        )
            elif bv != lv_v:
                all_diffs.append(f"  [{sid}] {key}: batch={bv!r} live={lv_v!r}")

    assert not all_diffs, (
        "SKEW DETECTED across full dataset:\n" + "\n".join(all_diffs)
    )


def test_ip_context_features_nonzero():
    """IP context features for a repeat session from 1.1.1.1 must be > 0."""
    live = run_live_pipeline(FIXTURE)

    # s7 is from 1.1.1.1 and comes 30s after s6 (same IP, well within 300 s)
    s7 = live.get("s7")
    assert s7 is not None, "Session s7 missing from live pipeline"
    assert s7["ip_sessions_last_300s"] >= 1, (
        f"s7 should see s6 in IP context; got ip_sessions_last_300s={s7['ip_sessions_last_300s']}"
    )

    # Verify batch agrees
    batch = run_batch_pipeline(FIXTURE)
    bs7 = batch.get("s7")
    assert bs7 is not None
    assert bs7["ip_sessions_last_300s"] == s7["ip_sessions_last_300s"], (
        "ip_sessions_last_300s differs between batch and live for s7"
    )
