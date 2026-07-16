"""Tests for ThreatIntelFeed and IOCEntry models.

Covers: model instantiation, column types, UUID default, timestamps auto-set.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.threat_intel import IOCEntry, ThreatIntelFeed


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session for model testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestThreatIntelFeed:
    def test_instantiation_with_required_fields(self):
        """ThreatIntelFeed can be created with provider_name."""
        feed = ThreatIntelFeed(provider_name="abuseipdb")
        assert feed.provider_name == "abuseipdb"
        assert feed.status == "active"
        assert feed.error_count == 0

    def test_uuid_is_auto_generated(self):
        """ThreatIntelFeed gets a UUID automatically."""
        feed = ThreatIntelFeed(provider_name="abuseipdb")
        assert isinstance(feed.id, uuid.UUID)

    def test_uuid_is_unique_per_instance(self):
        """Each ThreatIntelFeed instance gets a different UUID."""
        feed1 = ThreatIntelFeed(provider_name="abuseipdb")
        feed2 = ThreatIntelFeed(provider_name="otx")
        assert feed1.id != feed2.id

    def test_timestamps_are_set_on_creation(self):
        """created_at and updated_at are set when instantiated."""
        feed = ThreatIntelFeed(provider_name="abuseipdb")
        assert isinstance(feed.created_at, datetime)
        assert isinstance(feed.updated_at, datetime)

    def test_config_defaults_to_none(self):
        """config JSONB column defaults to None."""
        feed = ThreatIntelFeed(provider_name="abuseipdb")
        assert feed.config is None

    def test_config_accepts_dict(self):
        """config accepts a dict (JSONB)."""
        feed = ThreatIntelFeed(
            provider_name="abuseipdb",
            config={"api_key": "***", "timeout": 30},
        )
        assert feed.config["timeout"] == 30

    def test_status_default_is_active(self):
        """status defaults to 'active'."""
        feed = ThreatIntelFeed(provider_name="abuseipdb")
        assert feed.status == "active"

    def test_persists_to_db(self, db_session):
        """ThreatIntelFeed can be persisted to the database."""
        feed = ThreatIntelFeed(provider_name="abuseipdb")
        db_session.add(feed)
        db_session.commit()
        loaded = db_session.get(ThreatIntelFeed, feed.id)
        assert loaded is not None
        assert loaded.provider_name == "abuseipdb"


class TestIOCEntry:
    def test_instantiation_with_required_fields(self):
        """IOCEntry can be created with indicator, ioc_type, provider."""
        ioc = IOCEntry(
            indicator="1.2.3.4",
            ioc_type="ip",
            provider="abuseipdb",
            confidence=85,
        )
        assert ioc.indicator == "1.2.3.4"
        assert ioc.ioc_type == "ip"
        assert ioc.provider == "abuseipdb"
        assert ioc.confidence == 85

    def test_uuid_is_auto_generated(self):
        """IOCEntry gets a UUID automatically."""
        ioc = IOCEntry(
            indicator="1.2.3.4",
            ioc_type="ip",
            provider="abuseipdb",
            confidence=85,
        )
        assert isinstance(ioc.id, uuid.UUID)

    def test_timestamps_are_set_on_creation(self):
        """created_at and updated_at are set when instantiated."""
        ioc = IOCEntry(
            indicator="1.2.3.4",
            ioc_type="ip",
            provider="abuseipdb",
            confidence=85,
        )
        assert isinstance(ioc.created_at, datetime)
        assert isinstance(ioc.updated_at, datetime)

    def test_first_seen_last_seen_optional(self):
        """first_seen and last_seen can be None."""
        ioc = IOCEntry(
            indicator="evil.com",
            ioc_type="domain",
            provider="virustotal",
            confidence=90,
        )
        assert ioc.first_seen is None
        assert ioc.last_seen is None

    def test_expires_at_optional(self):
        """expires_at can be None."""
        ioc = IOCEntry(
            indicator="abc123def456",
            ioc_type="hash",
            provider="otx",
            confidence=70,
        )
        assert ioc.expires_at is None

    def test_confidence_range(self):
        """confidence stores integer value."""
        ioc = IOCEntry(
            indicator="10.0.0.1",
            ioc_type="ip",
            provider="abuseipdb",
            confidence=100,
        )
        assert ioc.confidence == 100

    def test_persists_to_db(self, db_session):
        """IOCEntry can be persisted to the database."""
        ioc = IOCEntry(
            indicator="1.2.3.4",
            ioc_type="ip",
            provider="abuseipdb",
            confidence=85,
        )
        db_session.add(ioc)
        db_session.commit()
        loaded = db_session.get(IOCEntry, ioc.id)
        assert loaded is not None
        assert loaded.indicator == "1.2.3.4"
        assert loaded.confidence == 85
