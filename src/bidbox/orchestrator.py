"""The orchestrator — chains the four agents through MCP-shaped operations.

The orchestrator is the entry point for `evaluate_bids`. It does NOT
write to the database directly — it returns a Report object that the
MCP tool layer persists. This separation makes the orchestrator easy
to test (no DB fixture needed) and keeps the human-in-the-loop boundary
clean (the agent layer has no write access to the decisions table).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import uuid4

from .agents import (
    AgentError,
    BidAnalyzerAgent,
    ExtractorAgent,
    RiskAgent,
    ScorerAgent,
)
from .gateway import Gateway
from .models import (
    Bid,
    BidEvaluation,
    Citation,
    Criterion,
    CriterionCategory,
    Report,
    RiskFlag,
    Score,
    Tender,
)
from .pdf import citation_for


@dataclass
class OrchestratorContext:
    """The immutable inputs to the orchestrator.

    Carries everything the orchestrator needs to evaluate a tender:
    the tender, its parsed paragraphs, the bids, and each bid's paragraphs.
    """

    tender: Tender
    tender_paragraphs: list[str]
    bids: list[Bid]
    bid_paragraphs: dict[str, list[str]]  # bid_id -> paragraphs


@dataclass
class OrchestratorResult:
    """The output of the orchestrator — a Report plus per-bid details.

    The MCP tool layer persists the Report; the per-bid details are
    stored separately (criteria, responses, scores, risk flags) so the
    review UI can render them.
    """

    report: Report
    criteria: list[Criterion]
    scores: list[Score]
    risk_flags: list[RiskFlag]
    ai_generated: bool = True


class OrchestratorAgent:
    """The orchestrator — chains Extractor → Analyzer → Scorer → Risk."""

    name = "orchestrator"
    version = "0.1.0"

    def __init__(self, gateway: Gateway) -> None:
        self._extractor = ExtractorAgent(gateway)
        self._analyzer = BidAnalyzerAgent(gateway)
        self._scorer = ScorerAgent(gateway)
        self._risk = RiskAgent(gateway)

    async def run(self, ctx: OrchestratorContext) -> OrchestratorResult:
        """Run the full evaluation workflow on a tender + its bids.

        Steps:
          1. ExtractorAgent  → criteria
          2. For each bid:
             a. BidAnalyzerAgent → responses per criterion
             b. ScorerAgent      → scores per (bid, criterion)
             c. RiskAgent        → risk flags
          3. Compose Report with ranked BidEvaluation per bid.
        """
        correlation_id = uuid4().hex
        total_tokens = 0
        total_cost = Decimal("0")

        # Step 1 — Extract criteria
        extractor_out = await self._extractor.run(ctx.tender.title, ctx.tender_paragraphs)
        total_tokens += extractor_out.tokens_used
        total_cost += extractor_out.cost_cents

        criteria: list[Criterion] = []
        for c in extractor_out.criteria:
            para_idx = c.get("citation_paragraph", 0)
            try:
                cit = citation_for(
                    document_id=f"doc-tender-{ctx.tender.id}",
                    paragraphs=ctx.tender_paragraphs,
                    index=para_idx,
                )
            except IndexError:
                # The LLM pointed to a paragraph that doesn't exist — drop the criterion.
                continue
            criteria.append(
                Criterion(
                    id=f"criterion-{ctx.tender.id}-{len(criteria)}",
                    tender_id=ctx.tender.id,
                    name=c["name"],
                    description=c["description"],
                    category=CriterionCategory(c.get("category", "other")),
                    weight=float(c.get("weight", 0.2)),
                    mandatory=bool(c.get("mandatory", False)),
                    citation=cit,
                    ai_generated=True,
                )
            )

        if not criteria:
            raise AgentError("extractor returned no criteria — cannot evaluate bids")

        # Step 2 — For each bid, run Analyzer + Scorer + Risk
        all_scores: list[Score] = []
        all_risks: list[RiskFlag] = []
        bid_evals: list[BidEvaluation] = []

        for bid in ctx.bids:
            paragraphs = ctx.bid_paragraphs.get(bid.id, [])
            if not paragraphs:
                # No paragraphs to analyze — skip but record empty
                bid_evals.append(
                    BidEvaluation(
                        bid_id=bid.id,
                        bidder_name=bid.bidder_name,
                        total_score=0.0,
                        weighted_score=0.0,
                        risk_flags=[],
                        recommendation="reject",
                        recommendation_rationale="Bid document contained no extractable text.",
                    )
                )
                continue

            # 2a — Analyzer
            criteria_dicts = [
                {
                    "name": c.name,
                    "description": c.description,
                    "category": c.category.value,
                    "mandatory": c.mandatory,
                    "weight": c.weight,
                }
                for c in criteria
            ]
            analyzer_out = await self._analyzer.run(bid.bidder_name, paragraphs, criteria_dicts)
            total_tokens += analyzer_out.tokens_used
            total_cost += analyzer_out.cost_cents

            # Map responses by criterion name
            responses_by_name: dict[str, dict[str, Any]] = {
                r["criterion_name"]: r for r in analyzer_out.responses
            }

            # 2b — Scorer
            criteria_with_responses = []
            for c in criteria:
                r = responses_by_name.get(c.name)
                response_text = r["response_text"] if r else "NOT FOUND IN BID"
                criteria_with_responses.append(
                    {
                        "name": c.name,
                        "description": c.description,
                        "weight": c.weight,
                        "mandatory": c.mandatory,
                        "response_text": response_text,
                    }
                )
            scorer_out = await self._scorer.run(bid.bidder_name, criteria_with_responses)
            total_tokens += scorer_out.tokens_used
            total_cost += scorer_out.cost_cents

            scores_by_name: dict[str, dict[str, Any]] = {
                s["criterion_name"]: s for s in scorer_out.scores
            }

            # Build Score objects with citations
            bid_scores: list[Score] = []
            for c in criteria:
                s = scores_by_name.get(c.name, {"score": 0.0, "rationale": "not scored"})
                # Citation for the bid response — try to find the cited paragraph
                r = responses_by_name.get(c.name)
                if r and r.get("citation_paragraph", -1) >= 0:
                    try:
                        bid_cit = citation_for(
                            document_id=f"doc-bid-{bid.id}",
                            paragraphs=paragraphs,
                            index=r["citation_paragraph"],
                        )
                    except IndexError:
                        bid_cit = c.citation  # fall back to tender citation
                else:
                    bid_cit = c.citation

                score = Score(
                    id=f"score-{bid.id}-{c.id}",
                    bid_id=bid.id,
                    criterion_id=c.id,
                    score=float(s.get("score", 0.0)),
                    rationale=s.get("rationale", ""),
                    citation_tender=c.citation,
                    citation_bid=bid_cit,
                    ai_generated=True,
                )
                bid_scores.append(score)
                all_scores.append(score)

            # 2c — Risk
            mandatory = [
                {"name": c.name, "description": c.description}
                for c in criteria
                if c.mandatory
            ]
            # Try to extract financial quote from the bid paragraphs
            financial_quote = _extract_financial_quote(paragraphs)
            risk_out = await self._risk.run(
                bid.bidder_name, paragraphs, mandatory, financial_quote
            )
            total_tokens += risk_out.tokens_used
            total_cost += risk_out.cost_cents

            bid_risks: list[RiskFlag] = []
            for r in risk_out.risk_flags:
                para_idx = r.get("citation_paragraph", -1)
                if para_idx >= 0 and para_idx < len(paragraphs):
                    try:
                        cit = citation_for(
                            document_id=f"doc-bid-{bid.id}",
                            paragraphs=paragraphs,
                            index=para_idx,
                        )
                    except IndexError:
                        cit = c.citation
                else:
                    # Use first paragraph as a placeholder citation (absence-based flag)
                    cit = Citation(
                        document_id=f"doc-bid-{bid.id}",
                        paragraph_index=0,
                        paragraph_text=paragraphs[0] if paragraphs else "",
                        similarity=0.0,
                    )
                rf = RiskFlag(
                    id=f"risk-{bid.id}-{len(bid_risks)}",
                    bid_id=bid.id,
                    risk_type=r["risk_type"],
                    severity=r["severity"],
                    description=r["description"],
                    citation=cit,
                    ai_generated=True,
                )
                bid_risks.append(rf)
                all_risks.append(rf)

            # Compose BidEvaluation
            total_score = sum(s.score for s in bid_scores)
            weighted = sum(s.score * c.weight for s, c in zip(bid_scores, criteria))
            has_critical = any(rf.severity == "critical" for rf in bid_risks)
            any_mandatory_zero = any(
                s.score == 0.0 and c.mandatory for s, c in zip(bid_scores, criteria)
            )

            if has_critical or any_mandatory_zero:
                recommendation = "reject"
                rec_rationale = "Bid has critical risk flags or missing mandatory criteria."
            elif weighted >= 7.0:
                recommendation = "award"
                rec_rationale = f"Weighted score {weighted:.2f}/10 — strong bid."
            elif weighted >= 5.0:
                recommendation = "shortlist"
                rec_rationale = f"Weighted score {weighted:.2f}/10 — borderline; recommend shortlist for negotiation."
            else:
                recommendation = "reject"
                rec_rationale = f"Weighted score {weighted:.2f}/10 — too low to shortlist."

            bid_evals.append(
                BidEvaluation(
                    bid_id=bid.id,
                    bidder_name=bid.bidder_name,
                    total_score=total_score,
                    weighted_score=weighted,
                    risk_flags=bid_risks,
                    recommendation=recommendation,
                    recommendation_rationale=rec_rationale,
                )
            )

        # Rank bids: award > shortlist > reject, then by weighted score desc
        rank_order = {"award": 0, "shortlist": 1, "reject": 2}
        bid_evals.sort(
            key=lambda b: (rank_order[b.recommendation], -b.weighted_score)
        )

        report = Report(
            tender_id=ctx.tender.id,
            bids=bid_evals,
            ai_generated=True,
            correlation_id=correlation_id,
            token_cost_cents=total_cost,
        )

        return OrchestratorResult(
            report=report,
            criteria=criteria,
            scores=all_scores,
            risk_flags=all_risks,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


import re

_FINANCIAL_PATTERNS = [
    r"(?:KES|KSh|KSH|Kenya Shillings|USD|US\$|\$)\s*([\d,]+(?:\.\d+)?)",
    r"([\d,]+(?:\.\d+)?)\s*(?:KES|KSh|KSH|Kenya Shillings|USD|US\$|\$)",
]


def _extract_financial_quote(paragraphs: list[str]) -> str | None:
    """Heuristic: find the first paragraph that looks like a financial quote."""
    for p in paragraphs:
        for pat in _FINANCIAL_PATTERNS:
            m = re.search(pat, p, re.IGNORECASE)
            if m:
                return p.strip()
    return None
