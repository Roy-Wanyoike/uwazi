"""The MCP server — exposes 7 tools that any MCP client can call.

The single most important tool is `record_officer_decision`: it is the
human-in-the-loop gate. It refuses any request where the principal is
an agent. The schema (CHECK + trigger) is the second line of defense.

Run the server:

    python -m bidbox.mcp_server                    # stdio (default)
    MCP_TRANSPORT=sse python -m bidbox.mcp_server   # HTTP/SSE

Connect from any MCP-compatible client (Claude Desktop, the MCP CLI,
a custom Python client, etc.).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from .agents import AgentError
from .citation import validate_citation
from .config import get_settings
from .db import Database, get_db, new_id
from .gateway import build_gateway
from .models import (
    AuditEntry,
    Bid,
    BidResponse,
    Criterion,
    CriterionCategory,
    Decision,
    DecisionType,
    Document,
    Principal,
    PrincipalKind,
    Tender,
)
from .orchestrator import OrchestratorAgent, OrchestratorContext
from .pdf import ingest_document


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------


mcp = FastMCP(
    "bidbox",
    instructions=(
        "BidBox — an agentic AI that evaluates public tenders for African "
        "procurement offices. AI recommends, the procurement officer decides.\n\n"
        "Tools:\n"
        "  - list_tenders\n"
        "  - ingest_tender\n"
        "  - ingest_bid\n"
        "  - evaluate_bids\n"
        "  - get_report\n"
        "  - record_officer_decision (HUMAN-ONLY — refuses agent principals)\n"
        "  - get_audit_trail\n"
    ),
)


# ---------------------------------------------------------------------------
# Tool: list_tenders
# ---------------------------------------------------------------------------


@mcp.tool()
def list_tenders() -> str:
    """List all ingested tenders.

    Returns a JSON array of {id, title, issuer, country_code, ingested_at}.
    Most recent first.
    """
    db = get_db()
    tenders = db.list_tenders()
    return json.dumps(
        [
            {
                "id": t.id,
                "title": t.title,
                "issuer": t.issuer,
                "country_code": t.country_code,
                "ingested_at": t.ingested_at.isoformat(),
            }
            for t in tenders
        ],
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool: ingest_tender
# ---------------------------------------------------------------------------


@mcp.tool()
def ingest_tender(
    path: str,
    tender_id: str | None = None,
    title: str | None = None,
    issuer: str = "Unknown Issuer",
    country_code: str = "KE",
) -> str:
    """Ingest a tender document (PDF or Markdown).

    The agent (or a human) provides the path to the document. The tool
    parses it into paragraphs, extracts the criteria via the
    ExtractorAgent, and stores everything. Returns the tender_id and
    the number of criteria extracted.

    NOTE: This tool is callable by both humans and agents. It writes
    to `tenders`, `documents`, `criteria` — never to `decisions`.
    """
    db = get_db()

    p = Path(path)
    if not p.exists():
        return json.dumps({"error": f"file not found: {path}"})

    tender_id = tender_id or new_id("tender")
    title = title or p.stem

    tender = Tender(
        id=tender_id,
        title=title,
        issuer=issuer,
        country_code=country_code,
        document_path=str(p),
    )
    db.save_tender(tender)

    # Parse the document
    doc = ingest_document(
        doc_id=f"doc-tender-{tender_id}",
        kind="tender",
        parent_id=tender_id,
        source_path=str(p),
    )
    db.save_document(doc)

    db.append_audit(
        AuditEntry(
            id=new_id("audit"),
            tender_id=tender_id,
            bid_id=None,
            entry_kind="tool_call",
            actor="mcp:ingest_tender",
            actor_kind=PrincipalKind.AGENT,
            payload={"path": str(p), "paragraphs": len(doc.paragraphs)},
        )
    )

    return json.dumps(
        {
            "tender_id": tender_id,
            "paragraphs": len(doc.paragraphs),
            "note": "criteria not yet extracted — call evaluate_bids to run the full workflow.",
        }
    )


# ---------------------------------------------------------------------------
# Tool: ingest_bid
# ---------------------------------------------------------------------------


@mcp.tool()
def ingest_bid(
    tender_id: str,
    path: str,
    bidder_name: str,
    bid_id: str | None = None,
) -> str:
    """Ingest a bid document against a tender.

    Returns the bid_id.
    """
    db = get_db()

    if db.get_tender(tender_id) is None:
        return json.dumps({"error": f"tender {tender_id} not found"})

    p = Path(path)
    if not p.exists():
        return json.dumps({"error": f"file not found: {path}"})

    bid_id = bid_id or new_id("bid")

    bid = Bid(
        id=bid_id,
        tender_id=tender_id,
        bidder_name=bidder_name,
        document_path=str(p),
    )
    db.save_bid(bid)

    doc = ingest_document(
        doc_id=f"doc-bid-{bid_id}",
        kind="bid",
        parent_id=bid_id,
        source_path=str(p),
    )
    db.save_document(doc)

    db.append_audit(
        AuditEntry(
            id=new_id("audit"),
            tender_id=tender_id,
            bid_id=bid_id,
            entry_kind="tool_call",
            actor="mcp:ingest_bid",
            actor_kind=PrincipalKind.AGENT,
            payload={"bidder": bidder_name, "paragraphs": len(doc.paragraphs)},
        )
    )

    return json.dumps({"bid_id": bid_id, "bidder_name": bidder_name, "paragraphs": len(doc.paragraphs)})


# ---------------------------------------------------------------------------
# Tool: evaluate_bids
# ---------------------------------------------------------------------------


@mcp.tool()
async def evaluate_bids(tender_id: str) -> str:
    """Run the agentic evaluation workflow on a tender.

    Chains: ExtractorAgent → BidAnalyzerAgent → ScorerAgent → RiskAgent
    → composes a ranked Report. All outputs are stamped ai_generated=True.
    The procurement officer reviews the report and records decisions
    via `record_officer_decision` — the agent NEVER writes decisions.

    Returns the report JSON.
    """
    db = get_db()
    settings = get_settings()

    tender = db.get_tender(tender_id)
    if tender is None:
        return json.dumps({"error": f"tender {tender_id} not found"})

    bids = db.list_bids(tender_id)
    if not bids:
        return json.dumps({"error": f"no bids ingested for tender {tender_id}"})

    tender_doc = db.get_document(f"doc-tender-{tender_id}")
    if tender_doc is None:
        return json.dumps({"error": f"tender document not found — was it ingested?"})

    bid_paragraphs: dict[str, list[str]] = {}
    for b in bids:
        bd = db.get_document(f"doc-bid-{b.id}")
        if bd is None:
            return json.dumps({"error": f"bid document for {b.id} not found"})
        bid_paragraphs[b.id] = bd.paragraphs

    ctx = OrchestratorContext(
        tender=tender,
        tender_paragraphs=tender_doc.paragraphs,
        bids=bids,
        bid_paragraphs=bid_paragraphs,
    )

    gateway = build_gateway(settings.llm)
    orchestrator = OrchestratorAgent(gateway)

    try:
        result = await orchestrator.run(ctx)
    except AgentError as exc:
        return json.dumps({"error": f"orchestrator failed: {exc}"})

    # Persist the orchestrator's outputs
    for c in result.criteria:
        db.save_criterion(c)

    for s in result.scores:
        db.save_score(s)

    for r in result.risk_flags:
        db.save_risk_flag(r)

    db.save_report(result.report)

    db.append_audit(
        AuditEntry(
            id=new_id("audit"),
            tender_id=tender_id,
            bid_id=None,
            entry_kind="ai_proposal",
            actor="orchestrator",
            actor_kind=PrincipalKind.AGENT,
            payload={
                "report_id": str(result.report.id),
                "bids": len(result.report.bids),
                "criteria": len(result.criteria),
                "scores": len(result.scores),
                "risk_flags": len(result.risk_flags),
                "token_cost_cents": str(result.report.token_cost_cents),
            },
        )
    )

    return json.dumps(
        {
            "report_id": str(result.report.id),
            "tender_id": tender_id,
            "bids_evaluated": len(result.report.bids),
            "criteria_extracted": len(result.criteria),
            "ranking": [
                {
                    "rank": i + 1,
                    "bid_id": b.bid_id,
                    "bidder_name": b.bidder_name,
                    "weighted_score": round(b.weighted_score, 2),
                    "recommendation": b.recommendation,
                    "rationale": b.recommendation_rationale,
                    "risk_flags": len(b.risk_flags),
                }
                for i, b in enumerate(result.report.bids)
            ],
            "ai_generated": True,
            "correlation_id": result.report.correlation_id,
            "note": "AI has proposed. The procurement officer must call record_officer_decision to finalize.",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool: get_report
# ---------------------------------------------------------------------------


@mcp.tool()
def get_report(tender_id: str) -> str:
    """Fetch the latest evaluation report for a tender.

    Returns the full report — per-bid scores, risk flags, citations,
    recommendation. The procurement officer reviews this and records
    decisions separately.
    """
    db = get_db()
    report = db.get_latest_report(tender_id)
    if report is None:
        return json.dumps({"error": f"no report found for tender {tender_id} — call evaluate_bids first"})

    # Enrich with scores and risk flags from the DB
    bids_out = []
    for b in report.bids:
        scores = db.list_scores(tender_id, b.bid_id)
        risks = db.list_risk_flags(b.bid_id)
        bids_out.append(
            {
                "bid_id": b.bid_id,
                "bidder_name": b.bidder_name,
                "total_score": round(b.total_score, 2),
                "weighted_score": round(b.weighted_score, 2),
                "recommendation": b.recommendation,
                "recommendation_rationale": b.recommendation_rationale,
                "scores": [
                    {
                        "score": s.score,
                        "rationale": s.rationale,
                        "citation_tender_paragraph": s.citation_tender.paragraph_text,
                        "citation_bid_paragraph": s.citation_bid.paragraph_text,
                    }
                    for s in scores
                ],
                "risk_flags": [
                    {
                        "risk_type": r.risk_type,
                        "severity": r.severity,
                        "description": r.description,
                        "citation_paragraph": r.citation.paragraph_text,
                    }
                    for r in risks
                ],
            }
        )

    return json.dumps(
        {
            "report_id": str(report.id),
            "tender_id": tender_id,
            "generated_at": report.generated_at.isoformat(),
            "ai_generated": report.ai_generated,
            "bids": bids_out,
            "note": "The agent has proposed. Call record_officer_decision to finalize each bid.",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool: record_officer_decision — HUMAN-ONLY
# ---------------------------------------------------------------------------


@mcp.tool()
def record_officer_decision(
    tender_id: str,
    bid_id: str,
    decision: str,
    rationale: str,
    principal_id: str,
    principal_kind: str = "human",
) -> str:
    """Record a procurement officer's decision on a bid.

    HUMAN-ONLY. This tool refuses any request where `principal_kind='agent'`.
    The SQL schema (CHECK + trigger) is the second line of defense — see
    ARCHITECTURE.md §5 (human-in-the-loop boundary).

    Args:
        tender_id: The tender being evaluated.
        bid_id: The bid being decided on.
        decision: One of 'accept', 'reject', 'needs_review'.
        rationale: The officer's rationale (free text, min 10 chars).
        principal_id: The officer's identifier.
        principal_kind: 'human' (default) — agents are refused.

    Returns the persisted decision.
    """
    # --- First line of defense: refuse agent principals ---
    if principal_kind == "agent":
        return json.dumps(
            {
                "error": "agents may not record decisions — human-in-the-loop rule (ARCHITECTURE.md §5)",
                "tender_id": tender_id,
                "bid_id": bid_id,
            }
        )

    # --- Validate the decision type ---
    try:
        decision_enum = DecisionType(decision)
    except ValueError:
        return json.dumps(
            {
                "error": f"invalid decision {decision!r} — must be one of: "
                f"{[d.value for d in DecisionType]}"
            }
        )

    # --- Validate rationale length ---
    if len(rationale.strip()) < 10:
        return json.dumps(
            {"error": "rationale must be at least 10 characters — explain the decision."}
        )

    db = get_db()

    # --- Persist ---
    d = Decision(
        id=new_id("decision"),
        tender_id=tender_id,
        bid_id=bid_id,
        decision=decision_enum,
        rationale=rationale,
        decided_by=principal_id,
    )

    try:
        db.save_decision(d)
    except Exception as exc:
        # The SQL trigger refuses agent-originated writes. Catch and report.
        if "agent may not record" in str(exc):
            return json.dumps(
                {
                    "error": "SQL trigger refused the insert — human-in-the-loop rule (ARCHITECTURE.md §5)",
                    "detail": str(exc),
                }
            )
        raise

    db.append_audit(
        AuditEntry(
            id=new_id("audit"),
            tender_id=tender_id,
            bid_id=bid_id,
            entry_kind="human_decision",
            actor=principal_id,
            actor_kind=PrincipalKind(principal_kind),
            payload={"decision": decision, "rationale": rationale},
        )
    )

    return json.dumps(
        {
            "decision_id": d.id,
            "tender_id": tender_id,
            "bid_id": bid_id,
            "decision": decision,
            "decided_by": principal_id,
            "decided_at": d.decided_at.isoformat(),
            "rationale": rationale,
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool: get_audit_trail
# ---------------------------------------------------------------------------


@mcp.tool()
def get_audit_trail(tender_id: str) -> str:
    """Fetch the full audit trail for a tender.

    Returns every AI proposal and every human decision, in chronological
    order. Exportable as a signed PDF for the procurement archive.
    """
    db = get_db()
    entries = db.list_audit(tender_id)
    decisions = db.list_decisions(tender_id)

    return json.dumps(
        {
            "tender_id": tender_id,
            "ai_proposals": [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat(),
                    "actor": e.actor,
                    "actor_kind": e.actor_kind.value,
                    "entry_kind": e.entry_kind,
                    "payload": e.payload,
                }
                for e in entries
                if e.entry_kind in ("ai_proposal", "tool_call")
            ],
            "human_decisions": [
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
            "note": "AI proposals are stamped ai_generated=True; decisions require a human principal.",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server with the configured transport."""
    settings = get_settings()
    if settings.mcp.transport == "sse":
        mcp.run(transport="sse", host=settings.mcp.sse_host, port=settings.mcp.sse_port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
