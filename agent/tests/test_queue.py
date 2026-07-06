"""Tests for agent.queue — SQLite WAL mode FIFO queue."""

import pytest
import tempfile
import os
import json
import time
from datetime import datetime, timezone

from agent.queue import EventQueue


class TestEventQueue:
    """EventQueue with SQLite backend."""

    @pytest.fixture
    def queue(self):
        """Create an EventQueue backed by a temporary file."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        q = EventQueue(db_path=tmp.name, max_size=100)
        yield q
        q.close()
        os.unlink(tmp.name)

    def test_enqueue_and_count(self, queue):
        """Enqueue adds an event and count returns 1."""
        queue.enqueue({"event_type": "login", "host": "srv01"})
        assert queue.count() == 1

    def test_dequeue_returns_events_fifo(self, queue):
        """Dequeue returns events in FIFO order."""
        queue.enqueue({"id": 1})
        queue.enqueue({"id": 2})
        queue.enqueue({"id": 3})
        events = queue.dequeue(batch_size=2)
        assert len(events) == 2
        assert events[0]["event_data"]["id"] == 1
        assert events[1]["event_data"]["id"] == 2

    def test_dequeue_all(self, queue):
        """Dequeue with large batch returns all pending."""
        queue.enqueue({"id": 1})
        queue.enqueue({"id": 2})
        events = queue.dequeue(batch_size=10)
        assert len(events) == 2

    def test_dequeue_empty(self, queue):
        """Dequeue on empty queue returns empty list."""
        events = queue.dequeue(batch_size=10)
        assert events == []

    def test_mark_sent(self, queue):
        """Mark_sent sets status to 'sent' for given IDs."""
        queue.enqueue({"id": 1})
        queue.enqueue({"id": 2})
        events = queue.dequeue(batch_size=10)
        ids = [e["id"] for e in events]
        queue.mark_sent(ids)
        assert queue.count() == 0
        # Dequeue again should return nothing
        assert queue.dequeue(batch_size=10) == []

    def test_mark_sent_empty(self, queue):
        """mark_sent with empty list does nothing."""
        queue.mark_sent([])  # should not raise

    def test_max_size_blocks_enqueue(self, queue):
        """Enqueue raises when max_size is reached."""
        # Fill to max_size (100)
        for i in range(100):
            queue.enqueue({"n": i})
        assert queue.count() == 100
        # Next enqueue should raise
        with pytest.raises(OverflowError, match="queue full"):
            queue.enqueue({"n": 101})

    def test_clear_old(self, queue):
        """clear_old removes events older than given days."""
        # Enqueue an event, then manipulate its created_at
        queue.enqueue({"test": "old"})
        # Directly update the timestamp to be 8 days old
        old_ts = (datetime.now(timezone.utc).timestamp() - 8 * 86400)
        queue._execute(
            "UPDATE events SET created_at = ? WHERE id = 1",
            (old_ts,),
        )
        # Enqueue a fresh event
        queue.enqueue({"test": "new"})
        assert queue.count() == 2
        queue.clear_old(days=7)
        assert queue.count() == 1

    def test_wal_mode_enabled(self, queue):
        """SQLite connection uses WAL journal mode."""
        row = queue._fetchone("PRAGMA journal_mode")
        assert row is not None
        # WAL mode may be reported as 'wal' (lowercase)
        assert row[0].lower() == "wal"

    def test_pending_status_on_enqueue(self, queue):
        """New events have status='pending'."""
        queue.enqueue({"msg": "hello"})
        row = queue._fetchone("SELECT status FROM events WHERE id = 1")
        assert row is not None
        assert row[0] == "pending"
