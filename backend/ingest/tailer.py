"""
backend/ingest/tailer.py
========================
Reliable file tailer for Cowrie JSON log files.

Features
--------
- Reads new lines appended to a file (like `tail -F`).
- Handles partial last lines (waits for newline before yielding).
- Handles malformed JSON (skip + count).
- Detects file truncation (size shrink -> seek to 0).
- Detects log rotation via inode change -> reopens file.
- POSIX and Windows compatible (no inotify dependency).
"""

import json
import logging
import os
import time
from typing import Generator, Optional, Tuple

logger = logging.getLogger(__name__)

# Poll interval when no new data is available
_POLL_INTERVAL = 0.1  # seconds


class LogTailer:
    """Tail a log file, yielding (parsed_event_dict, raw_line) tuples.

    Usage
    -----
    tailer = LogTailer(path)
    for event, raw in tailer.follow():
        process(event)

    For replay / one-shot reading, use tailer.read_from_start() which
    reads the entire file without blocking.
    """

    def __init__(
        self,
        path: str,
        start_offset: int = 0,
        start_inode: Optional[int] = None,
    ):
        self.path = path
        self._offset = start_offset
        self._last_inode = start_inode
        self._fh = None
        self.lines_read = 0
        self.malformed_lines = 0
        self._buf = ""          # partial-line buffer

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def offset(self) -> int:
        """Current byte offset in the file."""
        return self._offset

    @property
    def inode(self) -> Optional[int]:
        """Inode of the currently open file, or None."""
        return self._last_inode

    def read_from_start(self) -> Generator[Tuple[dict, str], None, None]:
        """Read the entire file from the beginning, non-blocking.

        Yields (event_dict, raw_line) for every parseable JSON line.
        Skips blank and malformed lines.
        """
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.rstrip("\n")
                if not raw.strip():
                    continue
                ev = self._try_parse(raw)
                if ev is not None:
                    yield ev, raw

    def follow(self, stop_event=None) -> Generator[Tuple[dict, str], None, None]:
        """Follow the file indefinitely, blocking between reads.

        stop_event: a threading.Event; set it to stop iteration.
        Yields (event_dict, raw_line) for each parseable JSON line.
        """
        while True:
            if stop_event and stop_event.is_set():
                break

            # Try to open / reopen the file if needed
            if self._fh is None:
                if not self._open_file():
                    time.sleep(_POLL_INTERVAL)
                    continue

            # Detect rotation: inode changed or file shrank
            try:
                stat = os.stat(self.path)
                cur_inode = self._get_inode(stat)
            except FileNotFoundError:
                logger.warning("Log file disappeared; waiting for rotation...")
                self._close()
                time.sleep(_POLL_INTERVAL)
                continue

            if cur_inode != self._last_inode:
                logger.info(
                    "Inode changed (%s -> %s); rotating log file.",
                    self._last_inode, cur_inode,
                )
                self._close()
                continue  # reopen next iteration

            if stat.st_size < self._offset:
                logger.warning(
                    "File shrunk (%d -> %d); assuming truncation; seeking to 0.",
                    self._offset, stat.st_size,
                )
                self._fh.seek(0)
                self._offset = 0
                self._buf = ""

            # Read new data
            chunk = self._fh.read(65536)
            if not chunk:
                time.sleep(_POLL_INTERVAL)
                continue

            self._offset = self._fh.tell()
            self._buf += chunk

            lines = self._buf.split("\n")
            # Keep the last (possibly partial) segment in the buffer
            self._buf = lines[-1]

            for raw in lines[:-1]:
                raw = raw.rstrip("\r")
                if not raw.strip():
                    continue
                self.lines_read += 1
                ev = self._try_parse(raw)
                if ev is not None:
                    yield ev, raw

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _open_file(self) -> bool:
        try:
            if os.name == "nt":
                import ctypes
                import msvcrt
                kernel32 = ctypes.windll.kernel32
                GENERIC_READ = 0x80000000
                FILE_SHARE_READ = 1
                FILE_SHARE_WRITE = 2
                FILE_SHARE_DELETE = 4
                OPEN_EXISTING = 3
                FILE_ATTRIBUTE_NORMAL = 128

                handle = kernel32.CreateFileW(
                    self.path,
                    GENERIC_READ,
                    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                    None,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    None,
                )
                if handle in (-1, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF):
                    return False
                fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
                fh = open(fd, "r", encoding="utf-8", errors="replace")
            else:
                fh = open(self.path, "r", encoding="utf-8", errors="replace")

            stat = os.stat(self.path)
            inode = self._get_inode(stat)

            if self._last_inode is not None and inode != self._last_inode:
                # Rotation detected immediately on open
                logger.info("New inode detected on open; starting from offset 0.")
                self._offset = 0

            self._last_inode = inode

            if self._offset > 0:
                try:
                    fh.seek(self._offset)
                except OSError:
                    fh.seek(0)
                    self._offset = 0

            self._fh = fh
            self._buf = ""
            return True
        except FileNotFoundError:
            return False

    def _close(self):
        if self._fh:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
        self._last_inode = None
        self._offset = 0
        self._buf = ""

    @staticmethod
    def _get_inode(stat) -> int:
        # On Windows st_ino is always 0; use a combination of
        # (dev, nlink, size_as_fallback) as a rotation proxy.
        if stat.st_ino != 0:
            return stat.st_ino
        # Windows fallback: use file identity via creation time if available
        ctime = getattr(stat, "st_ctime_ns", stat.st_ctime)
        return hash((stat.st_dev, ctime))

    def _try_parse(self, raw: str) -> Optional[dict]:
        try:
            ev = json.loads(raw)
            if not isinstance(ev, dict):
                self.malformed_lines += 1
                return None
            return ev
        except json.JSONDecodeError:
            self.malformed_lines += 1
            return None
