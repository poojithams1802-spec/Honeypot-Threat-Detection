"""
backend/ingest/session_tracker.py
==================================
In-memory session aggregation and feature computation for the live pipeline.

Responsibilities
----------------
- Accumulate events per session_id.
- Finalize a session when:
    (a) cowrie.session.closed arrives, or
    (b) no events for SESSION_IDLE_TIMEOUT_SEC seconds (marks incomplete).
- Compute base features via ml.features.extract_session_features (same fn
  as batch, zero skew).
- Apply IP-context via ml.features.IPContextTracker (same logic as batch).
- Cap memory: evict oldest sessions when active count exceeds MAX_ACTIVE_SESSIONS.
- Emit finalised session dicts to a callback.
"""

import logging
import os
import time
from collections import OrderedDict
from typing import Callable, Dict, List, Optional

from ml.features import extract_session_features, IPContextTracker
from ml.parse_logs import parse_iso8601

logger = logging.getLogger(__name__)

SESSION_IDLE_TIMEOUT_SEC = int(os.getenv("SESSION_IDLE_TIMEOUT_SEC", "120"))
MAX_ACTIVE_SESSIONS = int(os.getenv("MAX_ACTIVE_SESSIONS", "5000"))
IP_HISTORY_WINDOW_SEC = int(os.getenv("IP_HISTORY_WINDOW_SEC", "300"))

# Cowrie event ids we care about
VALID_EVENTIDS = {
    "cowrie.session.connect",
    "cowrie.client.version",
    "cowrie.login.failed",
    "cowrie.login.success",
    "cowrie.command.input",
    "cowrie.command.failed",
    "cowrie.session.file_download",
    "cowrie.session.file_upload",
    "cowrie.session.closed",
}


class SessionTracker:
    """Stateful in-memory tracker for active Cowrie sessions.

    Parameters
    ----------
    on_finalized : callable(session_features_dict) -> None
        Called synchronously whenever a session is finalized.
    ip_tracker : IPContextTracker
        Shared tracker; seed it from the DB before creating SessionTracker so
        that IP-context is warm on restart.
    is_demo : bool
        If True all finalised sessions are marked is_demo=True (replay mode).
    """

    def __init__(
        self,
        on_finalized: Callable[[dict], None],
        ip_tracker: Optional[IPContextTracker] = None,
        is_demo: bool = False,
    ):
        self._on_finalized = on_finalized
        self._ip_tracker = ip_tracker or IPContextTracker(max_sessions_per_ip=200)
        self._is_demo = is_demo

        # OrderedDict so we can evict oldest by order of insertion
        self._sessions: OrderedDict[str, dict] = OrderedDict()  # sid -> state
        self._metadata: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_event(self, event: dict) -> None:
        """Process one Cowrie event.

        Normalises the event, adds it to the appropriate session buffer,
        and finalises if a closed event is received.
        """
        eventid = event.get("eventid")
        if eventid not in VALID_EVENTIDS:
            return

        session_id = event.get("session")
        if not session_id:
            return

        # Normalise timestamp
        ts_str = event.get("timestamp", "")
        event["timestamp_sec"] = parse_iso8601(ts_str)

        # Get or create session state
        if session_id not in self._sessions:
            # Enforce memory cap by evicting oldest incomplete sessions
            while len(self._sessions) >= MAX_ACTIVE_SESSIONS:
                self._evict_oldest()

            self._sessions[session_id] = {
                "events": [],
                "last_seen": event["timestamp_sec"],
                "finalized": False,
            }
        else:
            # Move to end (most recently active)
            self._sessions.move_to_end(session_id)

        state = self._sessions[session_id]
        state["events"].append(event)
        state["last_seen"] = max(state["last_seen"], event["timestamp_sec"])

        if eventid == "cowrie.session.closed":
            self._finalize(session_id, incomplete=False)

    def flush_idle(self, now: Optional[float] = None) -> int:
        """Finalize sessions idle for longer than SESSION_IDLE_TIMEOUT_SEC.

        Returns the number of sessions flushed.
        Call this periodically from the ingestor main loop.
        """
        if now is None:
            now = time.time()
        cutoff = now - SESSION_IDLE_TIMEOUT_SEC
        to_flush = [
            sid for sid, state in self._sessions.items()
            if not state["finalized"] and state["last_seen"] < cutoff
        ]
        for sid in to_flush:
            self._finalize(sid, incomplete=True)
        return len(to_flush)

    def flush_all(self, now: Optional[float] = None) -> int:
        """Finalize ALL remaining active sessions (called on shutdown).

        Sessions that have no closed event are marked incomplete.
        """
        if now is None:
            now = time.time()
        active = [sid for sid, s in self._sessions.items() if not s["finalized"]]
        for sid in active:
            self._finalize(sid, incomplete=True)
        return len(active)

    @property
    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if not s["finalized"])

    @property
    def ip_tracker(self) -> IPContextTracker:
        return self._ip_tracker

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _finalize(self, session_id: str, incomplete: bool) -> None:
        state = self._sessions.get(session_id)
        if state is None or state["finalized"]:
            return

        state["finalized"] = True
        events = state["events"]

        # Base features
        feat = extract_session_features(events, session_id)
        if feat is None:
            logger.debug("Session %s has no events; skipping.", session_id)
            return

        # Override session_incomplete if we're force-flushing due to idle
        if incomplete:
            feat["session_incomplete"] = 1

        # IP-context: read BEFORE recording (strict-before semantics)
        ip = feat["src_ip"]
        ctx = self._ip_tracker.get_context(ip, feat["start_time"])
        feat.update(ctx)

        # Record into tracker so subsequent sessions from same IP see this one
        self._ip_tracker.record(feat)

        # Collect raw usernames, passwords, commands for detail view
        logins = [e for e in events if e.get("eventid") in ("cowrie.login.success", "cowrie.login.failed")]
        usernames = list({e.get("username") for e in logins if e.get("username")})
        passwords = list({e.get("password") for e in logins if e.get("password")})
        commands = [e.get("input", "") for e in events if e.get("eventid") == "cowrie.command.input" and "input" in e]
        self._metadata[session_id] = {
            "usernames": usernames,
            "passwords": passwords,
            "commands": commands,
        }

        # is_demo flag
        feat["is_demo"] = self._is_demo

        # Emit
        try:
            self._on_finalized(feat)
        except Exception as exc:
            logger.error("on_finalized callback error for %s: %s", session_id, exc)

    def pop_session_metadata(self, session_id: str) -> dict:
        """Retrieve and remove auxiliary session metadata (passwords, commands)."""
        return self._metadata.pop(session_id, {})

    def _evict_oldest(self) -> None:
        """Evict the oldest session (by insertion order) as incomplete."""
        if not self._sessions:
            return
        oldest_sid = next(iter(self._sessions))
        logger.warning(
            "Memory cap reached (%d); evicting session %s as incomplete.",
            MAX_ACTIVE_SESSIONS, oldest_sid,
        )
        self._finalize(oldest_sid, incomplete=True)
        # Remove from dict regardless (finalize may have already set flag)
        self._sessions.pop(oldest_sid, None)
