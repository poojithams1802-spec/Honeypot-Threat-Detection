import json
from datetime import datetime, timezone
import collections
import logging

def parse_iso8601(timestamp_str):
    if timestamp_str.endswith('Z'):
        timestamp_str = timestamp_str[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(timestamp_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0

def read_and_group_events(log_file_path):
    sessions = collections.defaultdict(list)
    malformed_lines = 0
    total_lines = 0

    valid_eventids = {
        "cowrie.session.connect", "cowrie.client.version", 
        "cowrie.login.failed", "cowrie.login.success", 
        "cowrie.command.input", "cowrie.command.failed", 
        "cowrie.session.file_download", "cowrie.session.file_upload", 
        "cowrie.session.closed"
    }

    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                total_lines += 1
                try:
                    event = json.loads(line.strip())
                    eventid = event.get('eventid')
                    if eventid not in valid_eventids:
                        continue
                    
                    session_id = event.get('session')
                    if not session_id:
                        continue
                    
                    event['timestamp_sec'] = parse_iso8601(event.get('timestamp', ''))
                    sessions[session_id].append(event)
                except json.JSONDecodeError:
                    malformed_lines += 1
    except FileNotFoundError:
        logging.warning(f"Log file not found: {log_file_path}")
    
    # Sort events by timestamp inside each session
    for session_id in sessions:
        sessions[session_id].sort(key=lambda e: e['timestamp_sec'])

    return sessions, total_lines, malformed_lines
