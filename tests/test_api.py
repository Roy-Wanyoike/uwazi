"""Regression tests for the HTTP API shapes consumed by the web app."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi.responses import JSONResponse

from uwazi import db as db_module
from uwazi.api import DecisionRequest, get_audit_trail, get_tender, record_decision, reseed
from uwazi.db import in_memory_db
from uwazi.models import (
    AuditEntry,
    Bid,
    BidEvaluation,
    Citation,
    Criterion,
    CriterionCategory,
    PrincipalKind,
    Report,
    RiskFlag,
    Score,
    Tender,
)


@pytest.fixture(autouse=True)
def setup_in_memory_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_module, "_DB", in_memory_db())


def _seed_report() -> None:
    db = db_module.get_db()
    tender = Tender(
        id="t1", title="Tender", issuer="Issuer", country_code="KE", document_path="t.md"
    )
    bid = Bid(id="b1", tender_id="t1", bidder_name="Bidder", document_path="b.md")
    citation = Citation(document_id="doc-tender-t1", paragraph_index=0, paragraph_text="Evidence")
    criterion = Criterion(
        id="c1",
        tender_id="t1",
        name="Capacity",
        description="Capacity evidence",
        category=CriterionCategory.TECHNICAL,
        weight=1.0,
        citation=citation,
    )
    score = Score(
        id="s1",
        bid_id="b1",
        criterion_id="c1",
        score=8.0,
        rationale="Strong evidence",
        citation_tender=citation,
        citation_bid=Citation(
            document_id="doc-bid-b1", paragraph_index=0, paragraph_text="Bid evidence"
        ),
    )
    risk = RiskFlag(
        id="r1",
        bid_id="b1",
        risk_type="review",
        severity="warning",
        description="Check supporting material",
        citation=score.citation_bid,
    )
    report = Report(
        tender_id="t1",
        bids=[
            BidEvaluation(
                bid_id="b1",
                bidder_name="Bidder",
                total_score=8.0,
                weighted_score=8.0,
                risk_flags=[risk],
                recommendation="award",
                recommendation_rationale="Highest score",
            )
        ],
        correlation_id="corr-1",
        token_cost_cents=Decimal("0"),
    )
    db.save_tender(tender)
    db.save_bid(bid)
    db.save_criterion(criterion)
    db.save_score(score)
    db.save_risk_flag(risk)
    db.save_report(report)


@pytest.mark.asyncio
async def test_tender_detail_includes_flattened_scores_and_citations() -> None:
    _seed_report()
    payload = await get_tender("t1")
    assert isinstance(payload, dict)
    report = payload["report"]
    assert report is not None
    bid = report["bids"][0]
    assert bid["scores"][0]["citation_bid_paragraph"] == "Bid evidence"
    assert bid["risk_flags"][0]["citation_paragraph"] == "Bid evidence"


@pytest.mark.asyncio
async def test_audit_endpoint_returns_ai_proposals() -> None:
    _seed_report()
    db_module.get_db().append_audit(
        AuditEntry(
            id="a1",
            tender_id="t1",
            bid_id=None,
            entry_kind="ai_proposal",
            actor="orchestrator",
            actor_kind=PrincipalKind.AGENT,
            payload={"report_id": "report-1"},
        )
    )
    payload = await get_audit_trail("t1")
    assert isinstance(payload, dict)
    assert payload["ai_proposals"][0]["actor"] == "orchestrator"


@pytest.mark.asyncio
async def test_decision_rejects_bid_from_another_tender() -> None:
    _seed_report()
    db = db_module.get_db()
    db.save_tender(
        Tender(id="t2", title="Other", issuer="Issuer", country_code="KE", document_path="t2.md")
    )
    db.save_bid(Bid(id="b2", tender_id="t2", bidder_name="Other", document_path="b2.md"))

    response = await record_decision(
        "t1",
        DecisionRequest(
            bid_id="b2",
            decision="accept",
            rationale="This bid belongs to a different tender.",
        ),
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    assert json.loads(bytes(response.body))["error"] == "bid not found for tender"


@pytest.mark.asyncio
async def test_reseed_is_disabled_without_admin_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UWAZI_ADMIN_TOKEN", raising=False)
    response = await reseed(None)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
