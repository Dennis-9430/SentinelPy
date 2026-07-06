"""SQLite-backed FIFO event queue with WAL mode.

Provides persistent buffering for events before they are sent to the server.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional


class EventQueue:
    """Thread-safe FIFO queue backed by SQLite with WAL mode.

    Stores events with status tracking (pending → sent).
    """

    def __init__(self, db_path: str, max_size: int = 10000):
        self._max_size = max_size
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT DEFAULT '',
                event_data TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_status
            ON events(status)
        """)
        self._conn.commit()

    def enqueue(self, event_data: dict) -> int:
        """Add an event to the queue.

        Args:
            event_data: Dictionary with event fields.

        Returns:
            The new row ID.

        Raises:
            OverflowError: If the queue has reached max_size pending events.
        """
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE status = 'pending'"
            )
            (count,) = cur.fetchone()
            if count >= self._max_size:
                raise OverflowError("Event queue full (max_size reached)")

            cur = self._conn.execute(
                "INSERT INTO events (event_data, status) VALUES (?, 'pending')",
                (json.dumps(event_data),),
            )
            self._conn.commit()
            return cur.lastrowid

    def dequeue(self, batch_size: int = 50) -> list[dict]:
        """Retrieve pending events in FIFO order.

        Args:
            batch_size: Maximum number of events to retrieve.

        Returns:
            List of dicts with keys: id, agent_id, event_data (parsed), status, created_at.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, agent_id, event_data, status, created_at "
                "FROM events WHERE status = 'pending' "
                "ORDER BY id ASC LIMIT ?",
                (batch_size,),
            ).fetchall()

        result = []
        for row in rows:
            event = dict(row)
            event["event_data"] = json.loads(event["event_data"])
            result.append(event)
        return result

    def mark_sent(self, ids: list[int]) -> None:
        """Mark events as sent by their IDs.

        Args:
            ids: List of event row IDs to mark as 'sent'.
        """
        if not ids:
            return
        with self._lock:
            placeholders = ",".join("?" for _ in ids)
            self._conn.execute(
                f"UPDATE events SET status = 'sent' WHERE id IN ({placeholders})",
                ids,
            )
            self._conn.commit()

    def count(self) -> int:
        """Return the number of events with status 'pending'."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM events WHERE status = 'pending'"
            )
            (count,) = cur.fetchone()
            return count

    def clear_old(self, days: int = 7) -> int:
        """Remove events older than the specified number of days.

        Args:
            days: Delete events older than this many days.

        Returns:
            Number of rows deleted.
        """
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM events WHERE created_at < datetime('now', ?)",
                (f"-{days} days",),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    # ── Test helpers ──────────────────────────────────────────────────────────

    def _execute(self, sql: str, params: tuple = ()) -> None:
        """Execute a raw SQL statement (for test use)."""
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _fetchone(self, sql: str) -> Optional[sqlite3.Row]:
        """Fetch a single row (for test use)."""
        cur = self._conn.execute(sql)
        return cur.fetchone()
