"""
ml/features.py - Feature extraction for Cowrie sessions.

NO TRAINING/SERVING SKEW guarantee
------------------------------------
One canonical implementation serves both batch (build_dataset) and live
(ingestor) pipelines:

  extract_session_features()  - stateless per-session base features
  IPContextTracker            - incremental IP-history state machine
      .get_context(ip, t)     - read context BEFORE registering the session
      .record(sess)           - register after context has been applied
      .seed_from_sessions()   - warm-start from DB on ingestor restart
  extract_all_features()      - batch wrapper driving IPContextTracker
"""

from ml.config import SUSPICIOUS_KEYWORDS
from collections import deque

_IP_HISTORY_WINDOW = 300  # seconds


# ---------------------------------------------------------------------------
# Per-session base features (stateless)
# ---------------------------------------------------------------------------

def extract_session_features(session_events, session_id):
    """Extract base features from events for one session.

    Returns a dict or None if session_events is empty.
    The returned dict does NOT yet contain ip_* context features.
    It DOES contain a temporary '_usernames' field (set) required by
    IPContextTracker; strip it before persisting to the DB.
    """
    if not session_events:
        return None

    start_time = session_events[0]["timestamp_sec"]
    end_time = session_events[-1]["timestamp_sec"]

    closed_events = [e for e in session_events if e["eventid"] == "cowrie.session.closed"]
    session_incomplete = 1 if not closed_events else 0
    if not session_incomplete:
        end_time = closed_events[-1]["timestamp_sec"]

    duration_sec = max(0, end_time - start_time)

    connect_events = [e for e in session_events if e["eventid"] == "cowrie.session.connect"]
    src_ip = connect_events[0].get("src_ip", "0.0.0.0") if connect_events else "0.0.0.0"
    dst_port = connect_events[0].get("dst_port", 2222) if connect_events else 2222
    protocol = 1 if dst_port in [23, 2223] else 0

    has_client_version = 1 if any(
        e["eventid"] == "cowrie.client.version" for e in session_events
    ) else 0

    logins = [
        e for e in session_events
        if e["eventid"] in ["cowrie.login.success", "cowrie.login.failed"]
    ]
    n_login_success = sum(1 for e in logins if e["eventid"] == "cowrie.login.success")
    n_login_failed = sum(1 for e in logins if e["eventid"] == "cowrie.login.failed")
    no_login_attempted = 1 if not logins else 0
    login_success_ratio = n_login_success / len(logins) if logins else 0.0

    usernames = set(e.get("username") for e in logins if "username" in e)
    passwords = set(e.get("password") for e in logins if "password" in e)
    n_unique_usernames = len(usernames)
    n_unique_passwords = len(passwords)

    avg_secs_between_logins = 0.0
    if len(logins) > 1:
        diffs = [logins[i]["timestamp_sec"] - logins[i - 1]["timestamp_sec"]
                 for i in range(1, len(logins))]
        avg_secs_between_logins = sum(diffs) / len(diffs)

    commands = [e for e in session_events if e["eventid"] == "cowrie.command.input"]
    n_commands = len(commands)
    n_failed_commands = sum(
        1 for e in session_events if e["eventid"] == "cowrie.command.failed"
    )
    unique_cmds = set(e.get("input", "") for e in commands)
    n_unique_commands = len(unique_cmds)

    avg_secs_between_commands = 0.0
    if len(commands) > 1:
        diffs = [commands[i]["timestamp_sec"] - commands[i - 1]["timestamp_sec"]
                 for i in range(1, len(commands))]
        avg_secs_between_commands = sum(diffs) / len(diffs)

    avg_command_length = (
        sum(len(e.get("input", "")) for e in commands) / n_commands
        if n_commands > 0 else 0.0
    )

    n_suspicious_commands = sum(
        1 for cmd in unique_cmds
        if any(kw in cmd for kw in SUSPICIOUS_KEYWORDS)
    )

    n_download_attempts = sum(
        1 for e in session_events if e["eventid"] == "cowrie.session.file_download"
    )
    n_file_uploads = sum(
        1 for e in session_events if e["eventid"] == "cowrie.session.file_upload"
    )

    return {
        "session_id": session_id,
        "src_ip": src_ip,
        "start_time": start_time,
        "end_time": end_time,
        "duration_sec": duration_sec,
        "protocol": protocol,
        "has_client_version": has_client_version,
        "n_login_failed": n_login_failed,
        "n_login_success": n_login_success,
        "login_success_ratio": login_success_ratio,
        "n_unique_usernames": n_unique_usernames,
        "n_unique_passwords": n_unique_passwords,
        "avg_secs_between_logins": avg_secs_between_logins,
        "n_commands": n_commands,
        "n_unique_commands": n_unique_commands,
        "n_failed_commands": n_failed_commands,
        "avg_secs_between_commands": avg_secs_between_commands,
        "avg_command_length": avg_command_length,
        "n_suspicious_commands": n_suspicious_commands,
        "n_download_attempts": n_download_attempts,
        "n_file_uploads": n_file_uploads,
        "no_login_attempted": no_login_attempted,
        "session_incomplete": session_incomplete,
        "_usernames": usernames,   # temporary; stripped by extract_all_features
    }


# ---------------------------------------------------------------------------
# IP Context Tracker  (incremental; shared between batch and live pipeline)
# ---------------------------------------------------------------------------

class IPContextTracker:
    """Maintain per-IP session history for computing IP-context features.

    The SAME object is used by both the batch pipeline and the live ingestor,
    ensuring identical feature computation (no training/serving skew).

    Protocol
    --------
    For each finalised session, IN chronological order:
        ctx  = tracker.get_context(ip, start_time)   # read FIRST
        sess.update(ctx)
        tracker.record(sess)                          # then record
    """

    def __init__(self, max_sessions_per_ip=0):
        """
        max_sessions_per_ip: cap deque length per IP (0 = unlimited).
        Batch uses 0; live ingestor should use a reasonable cap (e.g. 200).
        """
        self._history = {}   # ip -> deque of snapshot dicts
        self._max = max_sessions_per_ip

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_context(self, ip, start_time):
        """Return the 4 ip_* feature values for ip at start_time.

        Only sessions with start_time strictly within the 300-s window
        BEFORE start_time are included (matching batch behaviour).
        """
        history = self._prune(ip, start_time)
        all_usernames = set()
        for h in history:
            all_usernames.update(h.get("_usernames", set()))
        return {
            "ip_sessions_last_60s": sum(
                1 for h in history if start_time - h["start_time"] <= 60
            ),
            "ip_sessions_last_300s": len(history),
            "ip_failed_logins_last_300s": sum(h["n_login_failed"] for h in history),
            "ip_distinct_usernames_last_300s": len(all_usernames),
        }

    def record(self, sess):
        """Store a compact snapshot of sess in IP history."""
        ip = sess["src_ip"]
        if ip not in self._history:
            self._history[ip] = deque()
        snap = {
            "start_time": sess["start_time"],
            "n_login_failed": sess.get("n_login_failed", 0),
            "_usernames": sess.get("_usernames", set()),
        }
        self._history[ip].append(snap)
        if self._max and len(self._history[ip]) > self._max:
            self._history[ip].popleft()

    def seed_from_sessions(self, sessions):
        """Pre-populate history from previously finalised sessions.

        Accepts dicts with at least: src_ip, start_time, n_login_failed.
        Accepts _usernames (set) or usernames (list) for username reconstruction.
        Sessions are re-sorted by start_time internally.
        """
        for s in sorted(sessions, key=lambda x: x["start_time"]):
            if "_usernames" not in s:
                s = dict(s)
                s["_usernames"] = set(s.get("usernames") or [])
            self.record(s)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prune(self, ip, ref_time):
        """Return sessions for ip within _IP_HISTORY_WINDOW of ref_time."""
        if ip not in self._history:
            return []
        cutoff = ref_time - _IP_HISTORY_WINDOW
        pruned = deque(h for h in self._history[ip] if h["start_time"] > cutoff)
        self._history[ip] = pruned
        return list(pruned)


# ---------------------------------------------------------------------------
# Batch wrapper  (same public API as before)
# ---------------------------------------------------------------------------

def extract_all_features(sessions_dict):
    """Batch feature extraction for a dict of {session_id: [events]}.

    Processes sessions in chronological order and drives IPContextTracker so
    that ip_* features are byte-for-byte identical to what the live pipeline
    computes.

    Returns a list of feature dicts sorted by start_time.
    The temporary '_usernames' field is removed before returning.
    """
    features_list = []
    for session_id, events in sessions_dict.items():
        feat = extract_session_features(events, session_id)
        if feat:
            features_list.append(feat)

    features_list.sort(key=lambda x: x["start_time"])
    tracker = IPContextTracker()

    for sess in features_list:
        ctx = tracker.get_context(sess["src_ip"], sess["start_time"])
        sess.update(ctx)
        tracker.record(sess)

    for sess in features_list:
        sess.pop("_usernames", None)

    return features_list
