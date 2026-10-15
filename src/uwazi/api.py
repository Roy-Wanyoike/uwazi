"""FastAPI review UI — the procurement officer's screen.

The UI is intentionally minimal: a single page that lists tenders,
opens one, shows the ranked report (with one-click citation drill-down),
and lets the officer record `accept` / `reject` / `needs-review` decisions.

The decision POST endpoint refuses any request where `principal_kind='agent'`.
The SQL trigger is the second line of defense (see ARCHITECTURE.md §5).

On startup, if the DB is empty AND `AUTO_SEED_ON_START=true` (default),
the service auto-seeds the sample Makueni tender + 3 bids. This makes
the Vercel deployment self-contained — each cold start re-seeds the
ephemeral SQLite, so a judge visiting the deployed URL sees the demo
data immediately without running `python scripts/seed.py` themselves.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .config import get_settings
from .db import get_db, new_id
from .models import AuditEntry, Bid, Decision, DecisionType, Principal, PrincipalKind, Tender
from .pdf import ingest_document

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


# ---------------------------------------------------------------------------
# Lifespan — auto-seed on startup if DB is empty
# ---------------------------------------------------------------------------

# Path to the sample data directory. On a real install, this is the
# `samples/` folder at the repo root, resolved relative to this file.
SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "samples"
TENDER_PATH = SAMPLES_DIR / "tender-makueni-water.md"
BIDS = [
    ("bid-aquaforce", SAMPLES_DIR / "bid-aquaforce.md", "AquaForce Ltd"),
    ("bid-hydrotech", SAMPLES_DIR / "bid-hydrotech.md", "HydroTech Ltd"),
    ("bid-sahara", SAMPLES_DIR / "bid-sahara.md", "Sahara Civils Ltd"),
]
TENDER_ID = "makueni-water-2026"


def _seed_if_empty() -> dict:
    """Seed the sample tender + 3 bids if the DB has no tenders.

    Returns a summary dict — useful for the /admin/reseed endpoint.
    """
    db = get_db()
    existing = db.list_tenders()
    if existing:
        return {
            "already_seeded": True,
            "tender_count": len(existing),
            "skipped": True,
        }

    if not TENDER_PATH.exists():
        return {
            "already_seeded": False,
            "error": f"sample tender not found at {TENDER_PATH}",
            "skipped": True,
        }

    # Tender
    tender = Tender(
        id=TENDER_ID,
        title="Makueni County Water Reticulation Project",
        issuer="Government of Makueni County — Department of Water & Sanitation",
        country_code="KE",
        document_path=str(TENDER_PATH),
    )
    db.save_tender(tender)
    tender_doc = ingest_document(
        doc_id=f"doc-tender-{TENDER_ID}",
        kind="tender",
        parent_id=TENDER_ID,
        source_path=str(TENDER_PATH),
    )
    db.save_document(tender_doc)

    # Bids
    for bid_id, path, bidder_name in BIDS:
        if not path.exists():
            continue
        bid = Bid(
            id=bid_id,
            tender_id=TENDER_ID,
            bidder_name=bidder_name,
            document_path=str(path),
        )
        db.save_bid(bid)
        bid_doc = ingest_document(
            doc_id=f"doc-bid-{bid_id}",
            kind="bid",
            parent_id=bid_id,
            source_path=str(path),
        )
        db.save_document(bid_doc)

    return {
        "already_seeded": False,
        "tender_count": 1,
        "bid_count": sum(1 for _, p, _ in BIDS if p.exists()),
        "skipped": False,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan — runs once at startup (or on each cold start
    on Vercel serverless)."""
    auto_seed = os.environ.get("AUTO_SEED_ON_START", "true").lower() in ("1", "true", "yes")
    seed_result = {"skipped": True}
    if auto_seed:
        try:
            seed_result = _seed_if_empty()
        except Exception as exc:
            seed_result = {"error": str(exc), "skipped": True}
    app.state.seed_result = seed_result
    yield
    # shutdown — nothing to do.


app = FastAPI(
    title="Uwazi — Procurement Officer Review UI",
    description="The human-in-the-loop screen for Uwazi.",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Admin — manual re-seed trigger (useful on Vercel for resets)
# ---------------------------------------------------------------------------


@app.post("/api/v1/admin/reseed")
async def reseed() -> dict:
    """Drop all tenders/bids/documents and re-seed the sample data.

    Useful on Vercel: trigger this if the DB looks wrong, or to demo
    the seed → evaluate flow from a clean state.
    """
    db = get_db()
    # Order matters because of FK constraints
    with db.transaction() as conn:
        for table in ("audit_trail", "decisions", "reports", "risk_flags",
                      "scores", "responses", "criteria", "documents",
                      "bids", "tenders"):
            conn.execute(f"DELETE FROM {table}")
    result = _seed_if_empty()
    return {"reseeded": True, **result}


@app.get("/api/v1/admin/seed-status")
async def seed_status() -> dict:
    """Check whether the DB has been seeded and how many tenders/bids exist."""
    db = get_db()
    tenders = db.list_tenders()
    bid_count = sum(len(db.list_bids(t.id)) for t in tenders)
    return {
        "tender_count": len(tenders),
        "bid_count": bid_count,
        "tenders": [{"id": t.id, "title": t.title} for t in tenders],
        "auto_seed_on_start": os.environ.get("AUTO_SEED_ON_START", "true"),
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """The single-page review UI — served from web/index.html.
    On Vercel this route is shadowed by the Next.js frontend; the SPA
    is the local-dev fallback only."""
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/v1/open_notices")
async def open_notices_endpoint(country_code: str = "KE") -> dict:
    """Proxy to the MCP `open_notices` tool — so the Next.js frontend
    can call it via the FastAPI service without speaking MCP.

    Returns FACTS only (no AI inferences). Every claim is sourced from
    the stored tender + criteria."""
    from .db import get_db
    from .models import CriterionCategory
    db = get_db()
    tenders = [t for t in db.list_tenders() if t.country_code == country_code]
    notices = []
    for t in tenders:
        criteria = db.list_criteria(t.id)
        eligibility = [c for c in criteria if c.category == CriterionCategory.ELIGIBILITY]
        mandatory = [c for c in criteria if c.mandatory]
        notices.append({
            "tender_id": t.id,
            "title": t.title,
            "issuer": t.issuer,
            "country_code": t.country_code,
            "ingested_at": t.ingested_at.isoformat(),
            "criteria_count": len(criteria),
            "eligibility_checklist": [
                {"criterion": c.name, "description": c.description} for c in eligibility
            ],
            "mandatory_documents": [
                {"document": c.name, "description": c.description} for c in mandatory
            ],
            "apply_via": f"Call `ingest_bid` with tender_id={t.id} once you have prepared the mandatory documents.",
        })
    return {
        "country_code": country_code,
        "notices": notices,
        "note": "This is the citizen-facing layer — every claim here is FACT (not AI-generated).",
    }


# ---------------------------------------------------------------------------
# API — read-only views used by the page
# ---------------------------------------------------------------------------


@app.get("/api/v1/tenders")
async def list_tenders() -> dict:
    db = get_db()
    tenders = db.list_tenders()
    return {
        "tenders": [
            {
                "id": t.id,
                "title": t.title,
                "issuer": t.issuer,
                "country_code": t.country_code,
                "ingested_at": t.ingested_at.isoformat(),
                "bid_count": len(db.list_bids(t.id)),
            }
            for t in tenders
        ]
    }


@app.get("/api/v1/tenders/{tender_id}")
async def get_tender(tender_id: str) -> dict:
    db = get_db()
    tender = db.get_tender(tender_id)
    if tender is None:
        return JSONResponse({"error": "tender not found"}, status_code=404)
    bids = db.list_bids(tender_id)
    report = db.get_latest_report(tender_id)
    decisions = db.list_decisions(tender_id)
    audit = db.list_audit(tender_id)

    # Enrich the report with per-bid `scores` (the BidEvaluation model
    # only carries `risk_flags`, not scores — the scores live in the DB
    # separately by bid_id). The Next.js BidCard component reads
    # `bid.scores` and would throw TypeError on undefined otherwise.
    report_dict = None
    if report is not None:
        report_dict = report.model_dump(mode="json")
        for bid_eval in report_dict.get("bids", []):
            bid_id = bid_eval.get("bid_id")
            if bid_id:
                scores = db.list_scores(tender_id, bid_id)
                bid_eval["scores"] = [
                    {
                        "score": s.score,
                        "rationale": s.rationale,
                        "citation_tender_paragraph": s.citation_tender.paragraph_text,
                        "citation_bid_paragraph": s.citation_bid.paragraph_text,
                    }
                    for s in scores
                ]
            else:
                bid_eval["scores"] = []

    return {
        "tender": {
            "id": tender.id,
            "title": tender.title,
            "issuer": tender.issuer,
            "country_code": tender.country_code,
            "ingested_at": tender.ingested_at.isoformat(),
        },
        "bids": [
            {"id": b.id, "bidder_name": b.bidder_name, "ingested_at": b.ingested_at.isoformat()}
            for b in bids
        ],
        "report": report_dict,
        "decisions": [
            {
                "id": d.id,
                "bid_id": d.bid_id,
                "decision": d.decision.value,
                "decided_by": d.decided_by,
                "decided_at": d.decided_at.isoformat(),
                "rationale": d.rationale,
            }
            for d in decisions
        ],
        "audit_count": len(audit),
    }


# ---------------------------------------------------------------------------
# API — record a decision (HUMAN-ONLY)
# ---------------------------------------------------------------------------


class DecisionRequest(BaseModel):
    bid_id: str
    decision: Literal["accept", "reject", "needs_review"]
    rationale: str = Field(min_length=10)
    principal_id: str = "officer-demo"
    principal_kind: Literal["human", "agent"] = "human"


@app.post("/api/v1/tenders/{tender_id}/decisions")
async def record_decision(tender_id: str, req: DecisionRequest) -> dict:
    """Record a procurement officer's decision on a bid.

    HUMAN-ONLY — refuses `principal_kind='agent'`.
    """
    # First line of defense — refuse agent principals.
    if req.principal_kind == "agent":
        return JSONResponse(
            {
                "error": "agents may not record decisions — human-in-the-loop rule (ARCHITECTURE.md §5)",
            },
            status_code=403,
        )

    db = get_db()

    # Validate the tender + bid exist
    if db.get_tender(tender_id) is None:
        return JSONResponse({"error": "tender not found"}, status_code=404)

    d = Decision(
        id=new_id("decision"),
        tender_id=tender_id,
        bid_id=req.bid_id,
        decision=DecisionType(req.decision),
        rationale=req.rationale,
        decided_by=req.principal_id,
    )

    try:
        db.save_decision(d)
    except Exception as exc:
        if "agent may not record" in str(exc):
            return JSONResponse(
                {"error": "SQL trigger refused the insert", "detail": str(exc)},
                status_code=403,
            )
        raise

    db.append_audit(
        AuditEntry(
            id=new_id("audit"),
            tender_id=tender_id,
            bid_id=req.bid_id,
            entry_kind="human_decision",
            actor=req.principal_id,
            actor_kind=PrincipalKind(req.principal_kind),
            payload={"decision": req.decision, "rationale": req.rationale},
        )
    )

    return {
        "decision_id": d.id,
        "tender_id": tender_id,
        "bid_id": req.bid_id,
        "decision": req.decision,
        "decided_by": req.principal_id,
        "decided_at": d.decided_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# API — ingest (for the upload UI; same logic as the MCP tool)
# ---------------------------------------------------------------------------


class IngestTenderRequest(BaseModel):
    path: str
    title: str | None = None
    issuer: str = "Unknown Issuer"
    country_code: str = "KE"


@app.post("/api/v1/tenders")
async def ingest_tender(req: IngestTenderRequest) -> dict:
    db = get_db()
    p = Path(req.path)
    if not p.exists():
        return JSONResponse({"error": "file not found"}, status_code=404)

    tender_id = new_id("tender")
    from .models import Tender

    t = Tender(
        id=tender_id,
        title=req.title or p.stem,
        issuer=req.issuer,
        country_code=req.country_code,
        document_path=str(p),
    )
    db.save_tender(t)

    doc = ingest_document(
        doc_id=f"doc-tender-{tender_id}",
        kind="tender",
        parent_id=tender_id,
        source_path=str(p),
    )
    db.save_document(doc)
    return {"tender_id": tender_id, "paragraphs": len(doc.paragraphs)}


class IngestBidRequest(BaseModel):
    tender_id: str
    path: str
    bidder_name: str


@app.post("/api/v1/bids")
async def ingest_bid(req: IngestBidRequest) -> dict:
    db = get_db()
    if db.get_tender(req.tender_id) is None:
        return JSONResponse({"error": "tender not found"}, status_code=404)

    p = Path(req.path)
    if not p.exists():
        return JSONResponse({"error": "file not found"}, status_code=404)

    from .models import Bid

    bid_id = new_id("bid")
    b = Bid(
        id=bid_id,
        tender_id=req.tender_id,
        bidder_name=req.bidder_name,
        document_path=str(p),
    )
    db.save_bid(b)
    doc = ingest_document(
        doc_id=f"doc-bid-{bid_id}",
        kind="bid",
        parent_id=bid_id,
        source_path=str(p),
    )
    db.save_document(doc)
    return {"bid_id": bid_id, "paragraphs": len(doc.paragraphs)}


class EvaluateRequest(BaseModel):
    tender_id: str


@app.post("/api/v1/evaluate")
async def evaluate(req: EvaluateRequest) -> dict:
    """Trigger the agentic evaluation."""
    from .mcp_server import evaluate_bids

    result = await evaluate_bids(tender_id=req.tender_id)
    import json

    return json.loads(result) if isinstance(result, str) else result


@app.get("/api/v1/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "service": "uwazi-review-ui",
        "version": "0.1.0",
        "now": datetime.now(timezone.utc).isoformat(),
    }
