"""Tests for agent.watcher — file watching with watchdog and polling fallback."""

import pytest
import tempfile
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from agent.watcher import PollingWatcher, BaseWatcher, get_watcher


class TestPollingWatcher:
    """PollingWatcher using os.stat() to detect file changes."""

    @pytest.fixture
    def log_file(self):
        """Create a temporary log file."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False)
        tmp.close()
        yield Path(tmp.name)
        os.unlink(tmp.name)

    @pytest.fixture
    def watcher(self):
        """Create a PollingWatcher with fast poll interval."""
        w = PollingWatcher(poll_interval=0.05)
        yield w

    def test_yield_new_lines(self, watcher, log_file):
        """Watcher yields lines written after start."""
        watcher.watch(str(log_file))
        watcher.start()
        # Write lines
        with open(str(log_file), "a") as f:
            f.write("line1\nline2\n")
        result = watcher.poll()
        watcher.stop()
        assert str(log_file) in result
        assert result[str(log_file)] == ["line1\n", "line2\n"]

    def test_yield_only_new_lines(self, watcher, log_file):
        """Second poll yields only lines written after the first poll."""
        with open(str(log_file), "a") as f:
            f.write("old\n")
        watcher.watch(str(log_file))
        watcher.start()
        # First poll reads existing content
        first = watcher.poll()
        assert str(log_file) in first
        assert first[str(log_file)] == ["old\n"]
        # Write more
        with open(str(log_file), "a") as f:
            f.write("new\n")
        second = watcher.poll()
        assert str(log_file) in second
        assert second[str(log_file)] == ["new\n"]
        watcher.stop()

    def test_detect_truncate_resets_offset(self, watcher, log_file):
        """If file is truncated, watcher resets offset and reads from start."""
        with open(str(log_file), "a") as f:
            f.write("original\n")
        watcher.watch(str(log_file))
        watcher.start()
        watcher.poll()  # consume "original"
        # Truncate and write new content
        with open(str(log_file), "w") as f:
            f.write("fresh\n")
        result = watcher.poll()
        assert str(log_file) in result
        assert result[str(log_file)] == ["fresh\n"]
        watcher.stop()

    def test_no_new_lines(self, watcher, log_file):
        """Poll returns empty dict when no new data."""
        watcher.watch(str(log_file))
        watcher.start()
        result = watcher.poll()
        assert result == {}
        watcher.stop()

    def test_file_does_not_exist(self, watcher):
        """Poll returns empty dict for non-existent file (no crash)."""
        watcher.watch("/nonexistent/path.log")
        watcher.start()
        result = watcher.poll()
        assert result == {}
        watcher.stop()

    def test_multiple_watches(self, watcher):
        """Watcher tracks offsets for multiple files independently."""
        tmp1 = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False)
        tmp1.close()
        tmp2 = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False)
        tmp2.close()
        try:
            watcher.watch(tmp1.name)
            watcher.watch(tmp2.name)
            watcher.start()
            with open(tmp1.name, "a") as f:
                f.write("from1\n")
            with open(tmp2.name, "a") as f:
                f.write("from2\n")
            result = watcher.poll()
            watcher.stop()
            assert tmp1.name in result
            assert tmp2.name in result
            assert result[tmp1.name] == ["from1\n"]
            assert result[tmp2.name] == ["from2\n"]
        finally:
            os.unlink(tmp1.name)
            os.unlink(tmp2.name)


class TestGetWatcher:
    """Watcher factory."""

    def test_returns_base_watcher(self):
        """get_watcher returns a BaseWatcher instance."""
        w = get_watcher()
        assert isinstance(w, BaseWatcher)

    @patch("agent.watcher.watchdog_available", False)
    def test_returns_polling_when_watchdog_unavailable(self):
        """get_watcher returns PollingWatcher when watchdog is not available."""
        w = get_watcher()
        assert isinstance(w, PollingWatcher)
