"""Tests for the MCP tool surface — the public protocol layer.

Verifies that each tool returns the expected shape and that the
human-in-the-loop gate works correctly when called via the MCP tool
(the FastMCP wrapper).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from uwazi import db as db_module
from uwazi.db import in_memory_db
from uwazi.mcp_server import (
    evaluate_bids,
    fetch_tender_notice,
    get_audit_trail,
    get_report,
    ingest_bid,
    ingest_tender,
    list_tenders,
    record_officer_decision,
)

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture(autouse=True)
def setup_in_memory_db(monkeypatch: pytest.MonkeyPatch) -> None:
    db = in_memory_db()
    monkeypatch.setattr(db_module, "_DB", db)


# ---------------------------------------------------------------------------
# list_tenders
# ---------------------------------------------------------------------------


def test_list_tenders_empty() -> None:
    out = list_tenders()
    d = json.loads(out)
    assert d == []


def test_list_tenders_after_ingest() -> None:
    _ingest_sample_tender()
    out = list_tenders()
    d = json.loads(out)
    assert len(d) == 1
    assert d[0]["id"] == "makueni-water-2026"
    assert "Makueni" in d[0]["title"]


# ---------------------------------------------------------------------------
# ingest_tender
# ---------------------------------------------------------------------------


def test_ingest_tender_missing_file() -> None:
    out = ingest_tender(path="/nonexistent/path.md", tender_id="t-x")
    d = json.loads(out)
    assert "error" in d


def test_ingest_tender_sample() -> None:
    out = ingest_tender(
        path=str(SAMPLES_DIR / "tender-makueni-water.md"),
        tender_id="makueni-water-2026",
        title="Makueni County Water Reticulation Project",
        issuer="Government of Makueni County",
    )
    d = json.loads(out)
    assert d["tender_id"] == "makueni-water-2026"
    assert d["paragraphs"] > 0


@pytest.mark.asyncio
async def test_fetch_failure_without_tender_does_not_break_audit_fk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(_url: str) -> dict[str, Any]:
        return {"error": "offline", "fallback": True}

    monkeypatch.setattr("uwazi.mcp_server.fetch_url_via_external_mcp", unavailable)
    out = await fetch_tender_notice("https://example.invalid/tender")
    payload = json.loads(out)
    assert "error" in payload
    assert payload["external_mcp_server"] == "mcp-server-fetch"


# ---------------------------------------------------------------------------
# ingest_bid
# ---------------------------------------------------------------------------


def test_ingest_bid_unknown_tender() -> None:
    out = ingest_bid(
        tender_id="nonexistent",
        path=str(SAMPLES_DIR / "bid-aquaforce.md"),
        bidder_name="AquaForce",
    )
    d = json.loads(out)
    assert "error" in d


def test_ingest_bid_sample() -> None:
    _ingest_sample_tender()
    out = ingest_bid(
        tender_id="makueni-water-2026",
        path=str(SAMPLES_DIR / "bid-aquaforce.md"),
        bidder_name="AquaForce Ltd",
        bid_id="bid-aquaforce",
    )
    d = json.loads(out)
    assert d["bid_id"] == "bid-aquaforce"
    assert d["bidder_name"] == "AquaForce Ltd"
    assert d["paragraphs"] > 0


# ---------------------------------------------------------------------------
# evaluate_bids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_bids_full_workflow() -> None:
    _ingest_sample_tender()
    _ingest_sample_bids()
    out = await evaluate_bids(tender_id="makueni-water-2026")
    d = json.loads(out)
    assert "report_id" in d
    assert d["tender_id"] == "makueni-water-2026"
    assert d["bids_evaluated"] == 3
    assert d["criteria_extracted"] >= 1
    assert len(d["ranking"]) == 3
    assert d["ai_generated"] is True


@pytest.mark.asyncio
async def test_evaluate_bids_missing_tender() -> None:
    out = await evaluate_bids(tender_id="nonexistent")
    d = json.loads(out)
    assert "error" in d


# ---------------------------------------------------------------------------
# get_report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_report_after_evaluation() -> None:
    _ingest_sample_tender()
    _ingest_sample_bids()
    await evaluate_bids(tender_id="makueni-water-2026")
    out = get_report(tender_id="makueni-water-2026")
    d = json.loads(out)
    assert d["tender_id"] == "makueni-water-2026"
    assert d["ai_generated"] is True
    assert len(d["bids"]) == 3
    # Each bid should have scores + risk_flags
    for b in d["bids"]:
        assert "scores" in b
        assert "risk_flags" in b
        assert "recommendation" in b


def test_get_report_no_report_yet() -> None:
    _ingest_sample_tender()
    out = get_report(tender_id="makueni-water-2026")
    d = json.loads(out)
    assert "error" in d


# ---------------------------------------------------------------------------
# record_officer_decision — HUMAN-ONLY
# ---------------------------------------------------------------------------


def test_record_officer_decision_human() -> None:
    _ingest_sample_tender()
    _ingest_sample_bids()
    out = record_officer_decision(
        tender_id="makueni-water-2026",
        bid_id="bid-aquaforce",
        decision="accept",
        rationale="Highest scoring bid, meets all mandatory criteria.",
        principal_id="officer-1",
        principal_kind="human",
    )
    d = json.loads(out)
    assert d["decision"] == "accept"
    assert d["decided_by"] == "officer-1"


def test_record_officer_decision_agent_refused() -> None:
    _ingest_sample_tender()
    _ingest_sample_bids()
    out = record_officer_decision(
        tender_id="makueni-water-2026",
        bid_id="bid-aquaforce",
        decision="accept",
        rationale="agent attempt — should be refused",
        principal_id="uwazi-agent",
        principal_kind="agent",
    )
    d = json.loads(out)
    assert "error" in d
    assert "human-in-the-loop" in d["error"]


# ---------------------------------------------------------------------------
# get_audit_trail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_audit_trail_after_workflow() -> None:
    _ingest_sample_tender()
    _ingest_sample_bids()
    await evaluate_bids(tender_id="makueni-water-2026")
    record_officer_decision(
        tender_id="makueni-water-2026",
        bid_id="bid-aquaforce",
        decision="accept",
        rationale="Award to AquaForce — highest score.",
        principal_id="officer-1",
        principal_kind="human",
    )
    out = get_audit_trail(tender_id="makueni-water-2026")
    d = json.loads(out)
    assert d["tender_id"] == "makueni-water-2026"
    assert len(d["ai_proposals"]) >= 1  # the orchestrator proposal
    assert len(d["human_decisions"]) == 1
    assert d["human_decisions"][0]["decision"] == "accept"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ingest_sample_tender() -> None:
    ingest_tender(
        path=str(SAMPLES_DIR / "tender-makueni-water.md"),
        tender_id="makueni-water-2026",
        title="Makueni County Water Reticulation Project",
        issuer="Government of Makueni County",
    )


def _ingest_sample_bids() -> None:
    for bid_id, filename, bidder in [
        ("bid-aquaforce", "bid-aquaforce.md", "AquaForce Ltd"),
        ("bid-hydrotech", "bid-hydrotech.md", "HydroTech Ltd"),
        ("bid-sahara", "bid-sahara.md", "Sahara Civils Ltd"),
    ]:
        ingest_bid(
            tender_id="makueni-water-2026",
            path=str(SAMPLES_DIR / filename),
            bidder_name=bidder,
            bid_id=bid_id,
        )
