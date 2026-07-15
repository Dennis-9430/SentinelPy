"""Add performance indexes for SIEM query patterns

Revision ID: 008
Depends on: 007
"""

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

from alembic import op

# Names match the pattern: ix_<table>_<columns>
idx_events_source_ip = "ix_events_source_ip"
idx_events_severity_timestamp = "ix_events_severity_timestamp"
idx_events_type_timestamp = "ix_events_type_timestamp"
idx_alerts_created_at = "ix_alerts_created_at"
idx_alerts_status_severity = "ix_alerts_status_severity"
idx_alerts_status_created = "ix_alerts_status_created"
idx_rules_status = "ix_rules_status"
idx_rules_status_severity = "ix_rules_status_severity"
idx_rules_severity = "ix_rules_severity"


def upgrade() -> None:
    # ── Events ──────────────────────────────────────────────────────────
    op.create_index(idx_events_source_ip, "events", ["source_ip"])
    op.create_index(
        idx_events_severity_timestamp,
        "events",
        ["severity", "event_timestamp"],
    )
    op.create_index(
        idx_events_type_timestamp,
        "events",
        ["event_type", "event_timestamp"],
    )

    # ── Alerts ──────────────────────────────────────────────────────────
    op.create_index(idx_alerts_created_at, "alerts", ["created_at"])
    op.create_index(
        idx_alerts_status_severity,
        "alerts",
        ["status", "severity"],
    )
    op.create_index(
        idx_alerts_status_created,
        "alerts",
        ["status", "created_at"],
    )

    # ── Rules ───────────────────────────────────────────────────────────
    op.create_index(idx_rules_status, "rules", ["status"])
    op.create_index(idx_rules_severity, "rules", ["severity"])
    op.create_index(
        idx_rules_status_severity,
        "rules",
        ["status", "severity"],
    )


def downgrade() -> None:
    op.drop_index(idx_rules_status_severity, "rules")
    op.drop_index(idx_rules_severity, "rules")
    op.drop_index(idx_rules_status, "rules")
    op.drop_index(idx_alerts_status_created, "alerts")
    op.drop_index(idx_alerts_status_severity, "alerts")
    op.drop_index(idx_alerts_created_at, "alerts")
    op.drop_index(idx_events_type_timestamp, "events")
    op.drop_index(idx_events_severity_timestamp, "events")
    op.drop_index(idx_events_source_ip, "events")
