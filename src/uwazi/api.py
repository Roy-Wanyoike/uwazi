"""FastAPI review UI — the procurement officer's screen.

The UI is intentionally minimal: a single page that lists tenders,
opens one, shows the ranked report (with one-click citation drill-down),
and lets the officer record `accept` / `reject` / `needs-review` decisions.

The decision POST endpoint refuses any request where `principal_kind='agent'`.
The SQL trigger is the second line of defense (see ARCHITECTURE.md §5).

On startup, if the DB is empty AND `AUTO_SEED_ON_START=true` (default),
the service auto-seeds the sample Makueni tender + 3 bids. This makes
the Vercel deployment self-contained — each cold start re-seeds the
ephemeral SQLite, so a visitor opening the deployed URL sees the demo
data immediately without running `python scripts/seed.py` themselves.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .db import Database, get_db, new_id
from .models import AuditEntry, Bid, Decision, DecisionType, PrincipalKind, Report, Tender
from .pdf import ingest_document

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


# ---------------------------------------------------------------------------
# Lifespan — auto-seed on startup if DB is empty
# ---------------------------------------------------------------------------

# Path to the sample data directory. On a real install, this is the
# `samples/` folder at the repo root, resolved relative to this file.
SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "samples"

# All sample tenders + their bids. Auto-seeded on FastAPI startup if the
# DB is empty (so the Vercel deployment is self-contained — a visitor opening
# the deployed URL sees 5 tenders × 3 bids immediately).
TENDERS = [
    (
        "makueni-water-2026",
        "Makueni County Water Reticulation Project",
        "Government of Makueni County — Department of Water & Sanitation",
        SAMPLES_DIR / "tender-makueni-water.md",
        [
            ("bid-aquaforce", "AquaForce Ltd", SAMPLES_DIR / "bid-aquaforce.md"),
            ("bid-hydrotech", "HydroTech Ltd", SAMPLES_DIR / "bid-hydrotech.md"),
            ("bid-sahara", "Sahara Civils Ltd", SAMPLES_DIR / "bid-sahara.md"),
        ],
    ),
    (
        "nairobi-health-equipment-2026",
        "Nairobi County Hospital Equipment Supply",
        "Nairobi City County — Department of Health Services",
        SAMPLES_DIR / "tender-nairobi-health-equipment.md",
        [
            ("bid-nairobi-medequip", "MedEquip Africa Ltd", SAMPLES_DIR / "bid-nairobi-medequip.md"),
            ("bid-nairobi-healthtech", "HealthTech Distributors", SAMPLES_DIR / "bid-nairobi-healthtech.md"),
            ("bid-nairobi-sahara", "Sahara Medical Imports", SAMPLES_DIR / "bid-nairobi-sahara.md"),
        ],
    ),
    (
        "mombasa-road-rehab-2026",
        "Mombasa County Road Rehabilitation Project",
        "Mombasa County Government — Department of Roads & Public Works",
        SAMPLES_DIR / "tender-mombasa-road-rehab.md",
        [
            ("bid-mombasa-coastbuild", "CoastBuild Contractors Ltd", SAMPLES_DIR / "bid-mombasa-coastbuild.md"),
            ("bid-mombasa-highway", "Highway Civils Ltd", SAMPLES_DIR / "bid-mombasa-highway.md"),
            ("bid-mombasa-fasttrack", "FastTrack Civils", SAMPLES_DIR / "bid-mombasa-fasttrack.md"),
        ],
    ),
    (
        "kisumu-school-furniture-2026",
        "Kisumu County School Furniture Supply",
        "Kisumu County Government — Department of Education",
        SAMPLES_DIR / "tender-kisumu-school-furniture.md",
        [
            ("bid-kisumu-lakecraft", "LakeCraft Furniture Ltd", SAMPLES_DIR / "bid-kisumu-lakecraft.md"),
            ("bid-kisumu-comfort", "Comfort Seats Ltd", SAMPLES_DIR / "bid-kisumu-comfort.md"),
            ("bid-kisumu-lakeregion", "Lake Region Fabrications", SAMPLES_DIR / "bid-kisumu-lakeregion.md"),
        ],
    ),
    (
        "nakuru-solar-lighting-2026",
        "Nakuru County Solar Street Lighting Project",
        "Nakuru County Government — Department of Energy",
        SAMPLES_DIR / "tender-nakuru-solar-lighting.md",
        [
            ("bid-nakuru-solarbright", "SolarBright Africa Ltd", SAMPLES_DIR / "bid-nakuru-solarbright.md"),
            ("bid-nakuru-brightvolt", "BrightVolt Solutions", SAMPLES_DIR / "bid-nakuru-brightvolt.md"),
            ("bid-nakuru-sahara", "Sahara Solar Distributors", SAMPLES_DIR / "bid-nakuru-sahara.md"),
        ],
    ),
]


def _seed_if_empty() -> dict[str, Any]:
    """Seed any missing sample tenders + their bids.

    This is more nuanced than 'seed if empty': it compares the list of
    expected sample tenders to what's actually in the DB and ingests
    only the missing ones. So:
      - On a fresh cold start with empty DB → seeds all 5 tenders × 3 bids.
      - On a cold start where the DB has the old Makueni tender only
        (from a previous deploy) → ingests the 4 new tenders + their
        bids WITHOUT wiping the existing data.
      - On a cold start where the DB already has all 5 → skips entirely.

    Returns a summary dict — useful for the /admin/reseed endpoint.
    """
    db = get_db()
    existing_ids = {t.id for t in db.list_tenders()}

    if not SAMPLES_DIR.exists():
        return {
            "already_seeded": len(existing_ids) > 0,
            "tender_count": len(existing_ids),
            "error": f"samples directory not found at {SAMPLES_DIR}",
            "skipped": True,
        }

    # Build the list of tenders that need to be seeded (missing from DB).
    missing = [
        (tender_id, title, issuer, tender_path, bids)
        for tender_id, title, issuer, tender_path, bids in TENDERS
        if tender_id not in existing_ids
    ]
    if not missing:
        return {
            "already_seeded": True,
            "tender_count": len(existing_ids),
            "skipped": True,
        }

    tender_count = 0
    bid_count = 0
    for tender_id, title, issuer, tender_path, bids in missing:
        if not tender_path.exists():
            continue
        tender = Tender(
            id=tender_id,
            title=title,
            issuer=issuer,
            country_code="KE",
            document_path=str(tender_path),
        )
        db.save_tender(tender)
        tender_doc = ingest_document(
            doc_id=f"doc-tender-{tender_id}",
            kind="tender",
            parent_id=tender_id,
            source_path=str(tender_path),
        )
        db.save_document(tender_doc)
        tender_count += 1

        for bid_id, bidder_name, bid_path in bids:
            if not bid_path.exists():
                continue
            bid = Bid(
                id=bid_id,
                tender_id=tender_id,
                bidder_name=bidder_name,
                document_path=str(bid_path),
            )
            db.save_bid(bid)
            bid_doc = ingest_document(
                doc_id=f"doc-bid-{bid_id}",
                kind="bid",
                parent_id=bid_id,
                source_path=str(bid_path),
            )
            db.save_document(bid_doc)
            bid_count += 1

    return {
        "already_seeded": False,
        "tender_count": tender_count,
        "bid_count": bid_count,
        "skipped": False,
        "previously_existing_tenders": len(existing_ids),
        "total_tenders_after_seed": len(existing_ids) + tender_count,
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — runs once at startup (or on each cold start
    on Vercel serverless)."""
    auto_seed = os.environ.get("AUTO_SEED_ON_START", "true").lower() in ("1", "true", "yes")
    seed_result: dict[str, Any] = {"skipped": True}
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


@app.post("/api/v1/admin/reseed", response_model=None)
async def reseed(
    x_uwazi_admin_token: str | None = Header(default=None),
) -> dict[str, Any] | JSONResponse:
    """Drop all tenders/bids/documents and re-seed the sample data.

    Useful on Vercel: trigger this if the DB looks wrong, or to demo
    the seed → evaluate flow from a clean state.
    """
    expected_token = os.environ.get("UWAZI_ADMIN_TOKEN", "")
    if not expected_token:
        return JSONResponse(
            {"error": "reseed is disabled until UWAZI_ADMIN_TOKEN is configured"},
            status_code=503,
        )
    if not x_uwazi_admin_token or not secrets.compare_digest(x_uwazi_admin_token, expected_token):
        return JSONResponse({"error": "invalid admin token"}, status_code=403)

    db = get_db()
    # Order matters because of FK constraints
    with db.transaction() as conn:
        for table in (
            "audit_trail",
            "decisions",
            "reports",
            "risk_flags",
            "scores",
            "responses",
            "criteria",
            "documents",
            "bids",
            "tenders",
        ):
            conn.execute(f"DELETE FROM {table}")
    result = _seed_if_empty()
    return {"reseeded": True, **result}


@app.get("/api/v1/admin/seed-status")
async def seed_status() -> dict[str, Any]:
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
async def open_notices_endpoint(country_code: str = "KE") -> dict[str, Any]:
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
        notices.append(
            {
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
            }
        )
    return {
        "country_code": country_code,
        "notices": notices,
        "note": "This is the citizen-facing layer — every claim here is FACT (not AI-generated).",
    }


# ---------------------------------------------------------------------------
# API — read-only views used by the page
# ---------------------------------------------------------------------------


@app.get("/api/v1/tenders")
async def list_tenders() -> dict[str, Any]:
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


def _serialize_report(db: Database, report: Report | None) -> dict[str, Any] | None:
    """Return the report shape consumed by the Next.js review UI."""
    if report is None:
        return None

    bids = []
    for bid in report.bids:
        scores = db.list_scores(report.tender_id, bid.bid_id)
        risks = db.list_risk_flags(bid.bid_id)
        bids.append(
            {
                "bid_id": bid.bid_id,
                "bidder_name": bid.bidder_name,
                "total_score": bid.total_score,
                "weighted_score": bid.weighted_score,
                "recommendation": bid.recommendation,
                "recommendation_rationale": bid.recommendation_rationale,
                "scores": [
                    {
                        "score": score.score,
                        "rationale": score.rationale,
                        "citation_tender_paragraph": score.citation_tender.paragraph_text,
                        "citation_bid_paragraph": score.citation_bid.paragraph_text,
                    }
                    for score in scores
                ],
                "risk_flags": [
                    {
                        "risk_type": risk.risk_type,
                        "severity": risk.severity,
                        "description": risk.description,
                        "citation_paragraph": risk.citation.paragraph_text,
                    }
                    for risk in risks
                ],
            }
        )

    return {
        "id": str(report.id),
        "tender_id": report.tender_id,
        "generated_at": report.generated_at.isoformat(),
        "ai_generated": report.ai_generated,
        "bids": bids,
    }


@app.get("/api/v1/tenders/{tender_id}", response_model=None)
async def get_tender(tender_id: str) -> dict[str, Any] | JSONResponse:
    db = get_db()
    tender = db.get_tender(tender_id)
    if tender is None:
        return JSONResponse({"error": "tender not found"}, status_code=404)
    bids = db.list_bids(tender_id)
    report = db.get_latest_report(tender_id)
    decisions = db.list_decisions(tender_id)
    audit = db.list_audit(tender_id)

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
        "report": _serialize_report(db, report),
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


@app.get("/api/v1/tenders/{tender_id}/audit", response_model=None)
async def get_audit_trail(tender_id: str) -> dict[str, Any] | JSONResponse:
    """Return every AI/tool proposal and human decision for a tender."""
    db = get_db()
    if db.get_tender(tender_id) is None:
        return JSONResponse({"error": "tender not found"}, status_code=404)

    entries = db.list_audit(tender_id)
    decisions = db.list_decisions(tender_id)
    return {
        "tender_id": tender_id,
        "ai_proposals": [
            {
                "id": entry.id,
                "tender_id": entry.tender_id,
                "bid_id": entry.bid_id,
                "entry_kind": entry.entry_kind,
                "actor": entry.actor,
                "actor_kind": entry.actor_kind.value,
                "payload": entry.payload,
                "timestamp": entry.timestamp.isoformat(),
            }
            for entry in entries
            if entry.entry_kind in ("ai_proposal", "tool_call")
        ],
        "human_decisions": [
            {
                "id": decision.id,
                "bid_id": decision.bid_id,
                "decision": decision.decision.value,
                "decided_by": decision.decided_by,
                "decided_at": decision.decided_at.isoformat(),
                "rationale": decision.rationale,
            }
            for decision in decisions
        ],
        "note": "AI proposals are stamped agent; decisions require a human principal.",
    }


# ---------------------------------------------------------------------------
# API — record a decision (HUMAN-ONLY)
# ---------------------------------------------------------------------------


class DecisionRequest(BaseModel):
    bid_id: str
    decision: Literal["accept", "reject", "needs_review"]
    rationale: str = Field(min_length=10)
    principal_id: str = Field(default="officer-demo", min_length=1)
    principal_kind: Literal["human", "agent"] = "human"


@app.post("/api/v1/tenders/{tender_id}/decisions", response_model=None)
async def record_decision(tender_id: str, req: DecisionRequest) -> dict[str, Any] | JSONResponse:
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
    bid = db.get_bid(req.bid_id)
    if bid is None or bid.tender_id != tender_id:
        return JSONResponse({"error": "bid not found for tender"}, status_code=404)

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


@app.post("/api/v1/tenders", response_model=None)
async def ingest_tender(req: IngestTenderRequest) -> dict[str, Any] | JSONResponse:
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
    doc = ingest_document(
        doc_id=f"doc-tender-{tender_id}",
        kind="tender",
        parent_id=tender_id,
        source_path=str(p),
    )
    db.save_tender(t)
    db.save_document(doc)
    return {"tender_id": tender_id, "paragraphs": len(doc.paragraphs)}


class IngestBidRequest(BaseModel):
    tender_id: str
    path: str
    bidder_name: str


@app.post("/api/v1/bids", response_model=None)
async def ingest_bid(req: IngestBidRequest) -> dict[str, Any] | JSONResponse:
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
    doc = ingest_document(
        doc_id=f"doc-bid-{bid_id}",
        kind="bid",
        parent_id=bid_id,
        source_path=str(p),
    )
    db.save_bid(b)
    db.save_document(doc)
    return {"bid_id": bid_id, "paragraphs": len(doc.paragraphs)}


class EvaluateRequest(BaseModel):
    tender_id: str


@app.post("/api/v1/evaluate", response_model=None)
async def evaluate(req: EvaluateRequest) -> dict[str, Any] | JSONResponse:
    """Trigger the agentic evaluation."""
    from .mcp_server import evaluate_bids

    result = await evaluate_bids(tender_id=req.tender_id)
    import json

    data: Any = json.loads(result) if isinstance(result, str) else result
    if not isinstance(data, dict):
        return JSONResponse({"error": "evaluation returned an invalid response"}, status_code=502)
    if "error" in data:
        status_code = 404 if "not found" in str(data["error"]) else 400
        return JSONResponse(data, status_code=status_code)
    return data


@app.get("/api/v1/healthz")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "uwazi-review-ui",
        "version": "0.1.0",
        "now": datetime.now(UTC).isoformat(),
    }
