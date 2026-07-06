"""File watcher with watchdog and native polling fallback.

Tracks per-file offsets and detects truncation to handle log rotation.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

# Check if watchdog is available
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    watchdog_available = True
except ImportError:
    watchdog_available = False


def _read_new_lines(path: str, last_offset: int) -> tuple[list[str], int]:
    """Read new lines from a file since the given offset.

    Args:
        path: File path to read from.
        last_offset: Byte offset to start reading from.

    Returns:
        Tuple of (lines, new_offset).
        Handles file not existing, truncation, and normal appends.
    """
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return [], last_offset

    current_size = st.st_size

    # Detect truncation: file got smaller
    if current_size < last_offset:
        last_offset = 0

    if current_size == last_offset:
        return [], last_offset

    # Read new content
    try:
        with open(path, "rb") as f:
            f.seek(last_offset)
            data = f.read(current_size - last_offset)
    except (OSError, IOError):
        return [], last_offset

    new_offset = current_size

    if not data:
        return [], new_offset

    # Decode and split into lines — normalize \r\n to \n
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    parts = text.split("\n")
    # Every part except the last is a complete line (the \n was stripped)
    lines = [p + "\n" for p in parts[:-1]]
    # If the text ends with \n, the last part is empty string → no partial line
    if text.endswith("\n"):
        return lines, new_offset
    # Otherwise the last part is a partial line
    if parts[-1]:
        lines.append(parts[-1])
    return lines, new_offset


class BaseWatcher(ABC):
    """Abstract base for file watchers."""

    @abstractmethod
    def watch(self, path: str) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def poll(self) -> dict[str, list[str]]: ...

    @abstractmethod
    def stop(self) -> None: ...


# ── Polling Fallback ─────────────────────────────────────────────────────────


class PollingWatcher(BaseWatcher):
    """Polling-based file watcher using os.stat().

    Periodically checks file sizes and reads new lines since the last offset.
    Detects truncation (file size < last offset) and resets to 0.
    """

    def __init__(self, poll_interval: float = 1.0):
        self._poll_interval = poll_interval
        self._watched: dict[str, int] = {}  # path → last offset
        self._running = False

    def watch(self, path: str) -> None:
        """Register a file path to watch."""
        if path not in self._watched:
            self._watched[path] = 0

    def start(self) -> None:
        """Start monitoring (no-op for polling — state tracking only)."""
        self._running = True

    def poll(self) -> dict[str, list[str]]:
        """Check all watched files for new lines.

        Returns:
            Dict mapping file path → list of new lines since the last poll.
        """
        result: dict[str, list[str]] = {}
        for path in list(self._watched.keys()):
            new_lines, new_offset = _read_new_lines(path, self._watched[path])
            self._watched[path] = new_offset
            if new_lines:
                result[path] = new_lines
        return result

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False


# ── Watchdog-based watcher (when available) ──────────────────────────────────


if watchdog_available:

    class WatchdogHandler(FileSystemEventHandler):
        """EventHandler that collects modified file paths."""

        def __init__(self):
            self.modified: set[str] = set()

        def on_modified(self, event):
            if not event.is_directory:
                self.modified.add(event.src_path)

    class WatchdogWatcher(BaseWatcher):
        """Watchdog-based watcher using filesystem events."""

        def __init__(self, poll_interval: float = 1.0):
            self._poll_interval = poll_interval
            self._handler = WatchdogHandler()
            self._observer = Observer()
            self._watched: dict[str, int] = {}
            self._running = False

        def watch(self, path: str) -> None:
            if path not in self._watched:
                self._watched[path] = 0
                self._observer.schedule(self._handler, os.path.dirname(path) or ".", recursive=False)

        def start(self) -> None:
            self._running = True
            self._observer.start()

        def poll(self) -> dict[str, list[str]]:
            result: dict[str, list[str]] = {}
            # Process files flagged by watchdog events
            modified = self._handler.modified.copy()
            self._handler.modified.clear()
            for path in modified:
                if path in self._watched:
                    new_lines, new_offset = _read_new_lines(path, self._watched[path])
                    self._watched[path] = new_offset
                    if new_lines:
                        result[path] = new_lines
            return result

        def stop(self) -> None:
            self._running = False
            self._observer.stop()
            self._observer.join()


def get_watcher(poll_interval: float = 1.0) -> BaseWatcher:
    """Return the best available watcher.

    Uses watchdog if available, otherwise falls back to polling.
    """
    if watchdog_available:
        return WatchdogWatcher(poll_interval=poll_interval)
    return PollingWatcher(poll_interval=poll_interval)
