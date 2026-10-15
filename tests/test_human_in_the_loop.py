"""Tests for the human-in-the-loop boundary.

These tests verify the architectural rule from ARCHITECTURE.md §5:
the agent may NEVER record a decision. Enforced at three layers:
  1. SQL — CHECK constraint + BEFORE INSERT trigger
  2. Tool layer — `record_officer_decision` refuses agent principals
  3. Process — this test suite runs on every commit
"""
from __future__ import annotations

import json

import pytest

from uwazi.db import in_memory_db
from uwazi.models import Decision, DecisionType
from uwazi.mcp_server import record_officer_decision
from uwazi import db as db_module


@pytest.fixture(autouse=True)
def setup_in_memory_db(monkeypatch) -> None:
    """Replace the global DB with an in-memory one for every test."""
    db = in_memory_db()
    # Seed a tender + bid so the FK references resolve
    db._conn.execute(
        "INSERT INTO tenders (id, title, issuer, country_code, document_path, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("t1", "Test Tender", "Test Issuer", "KE", "/tmp/test.md", "2026-10-15T00:00:00Z"),
    )
    db._conn.execute(
        "INSERT INTO bids (id, tender_id, bidder_name, document_path, ingested_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("b1", "t1", "Bidder One", "/tmp/bid.md", "2026-10-15T00:00:00Z"),
    )
    monkeypatch.setattr(db_module, "_DB", db)


# ---------------------------------------------------------------------------
# SQL layer — CHECK constraint + trigger
# ---------------------------------------------------------------------------


def test_sql_trigger_refuses_agent_writer() -> None:
    """The SQL trigger must refuse any insert with decided_by='agent'."""
    db = in_memory_db()
    db._conn.execute(
        "INSERT INTO tenders (id, title, issuer, country_code, document_path, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("t2", "T2", "I", "KE", "/t2.md", "2026-10-15T00:00:00Z"),
    )
    db._conn.execute(
        "INSERT INTO bids (id, tender_id, bidder_name, document_path, ingested_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("b2", "t2", "B", "/b2.md", "2026-10-15T00:00:00Z"),
    )

    # Try to insert a decision with decided_by='agent'
    with pytest.raises(Exception) as exc_info:
        db._conn.execute(
            "INSERT INTO decisions (id, tender_id, bid_id, decision, rationale, decided_by, decided_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("d1", "t2", "b2", "accept", "agent attempt", "agent", "2026-10-15T00:00:00Z"),
        )
    assert "agent may not record" in str(exc_info.value)


def test_check_constraint_refuses_invalid_decision() -> None:
    """The CHECK constraint must refuse invalid decision values."""
    db = in_memory_db()
    db._conn.execute(
        "INSERT INTO tenders (id, title, issuer, country_code, document_path, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("t3", "T3", "I", "KE", "/t3.md", "2026-10-15T00:00:00Z"),
    )
    db._conn.execute(
        "INSERT INTO bids (id, tender_id, bidder_name, document_path, ingested_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("b3", "t3", "B", "/b3.md", "2026-10-15T00:00:00Z"),
    )
    with pytest.raises(Exception):
        db._conn.execute(
            "INSERT INTO decisions (id, tender_id, bid_id, decision, rationale, decided_by, decided_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("d2", "t3", "b3", "approved", "x" * 20, "officer-1", "2026-10-15T00:00:00Z"),
        )


# ---------------------------------------------------------------------------
# Tool layer — record_officer_decision refuses agent principals
# ---------------------------------------------------------------------------


def test_tool_refuses_agent_principal() -> None:
    """The MCP tool must refuse requests where principal_kind='agent'."""
    result = record_officer_decision(
        tender_id="t1",
        bid_id="b1",
        decision="accept",
        rationale="agent attempt — should be refused",
        principal_id="uwazi-agent",
        principal_kind="agent",
    )
    d = json.loads(result)
    assert "error" in d
    assert "human-in-the-loop" in d["error"]
    assert "tender_id" in d  # the tool returns context


def test_tool_accepts_human_principal() -> None:
    """The MCP tool must accept requests where principal_kind='human'."""
    result = record_officer_decision(
        tender_id="t1",
        bid_id="b1",
        decision="accept",
        rationale="AquaForce bid meets all mandatory criteria and scores highest.",
        principal_id="officer-1",
        principal_kind="human",
    )
    d = json.loads(result)
    assert d.get("decision") == "accept"
    assert d.get("decided_by") == "officer-1"
    assert "decision_id" in d


def test_tool_refuses_short_rationale() -> None:
    """The tool must refuse rationales shorter than 10 chars."""
    result = record_officer_decision(
        tender_id="t1",
        bid_id="b1",
        decision="accept",
        rationale="ok",  # too short
        principal_id="officer-1",
        principal_kind="human",
    )
    d = json.loads(result)
    assert "error" in d
    assert "rationale" in d["error"].lower()


def test_tool_refuses_invalid_decision_type() -> None:
    """The tool must refuse invalid decision values."""
    result = record_officer_decision(
        tender_id="t1",
        bid_id="b1",
        decision="approved",  # invalid — must be 'accept'/'reject'/'needs_review'
        rationale="invalid decision type attempt",
        principal_id="officer-1",
        principal_kind="human",
    )
    d = json.loads(result)
    assert "error" in d
    assert "invalid decision" in d["error"].lower()
