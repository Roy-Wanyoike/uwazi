"""Pydantic domain models for BidBox.

These types are the contract between the MCP tools, the agent, the
storage layer, and the review UI. They are deliberately explicit: every
AI output carries `ai_generated=True`, every claim carries citations,
every decision carries a human principal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Principals — who is calling the tool?
# ---------------------------------------------------------------------------


class PrincipalKind(str, Enum):
    """The kind of caller making an MCP request.

    `record_officer_decision` refuses any request where `kind='agent'`.
    See ARCHITECTURE.md §5 (human-in-the-loop boundary).
    """

    HUMAN = "human"
    AGENT = "agent"


class Principal(BaseModel):
    """The identity making an MCP call.

    In production, this is extracted from the OIDC token. In the demo,
    it is hardcoded via the `HumanInTheLoopConfig`.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    kind: PrincipalKind
    display_name: str = ""

    @classmethod
    def officer_demo(cls) -> "Principal":
        """The demo procurement officer principal."""
        return cls(id="officer-demo", kind=PrincipalKind.HUMAN, display_name="Demo Officer")

    @classmethod
    def agent(cls) -> "Principal":
        """The agent principal — used for AI-originated tool calls."""
        return cls(id="bidbox-agent", kind=PrincipalKind.AGENT, display_name="BidBox Agent")


# ---------------------------------------------------------------------------
# Citations — paragraph-level pointers into source documents
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    """A citation to a paragraph in a source document.

    Citations are paragraph-level, not page-level — see ADR-0002 in
    ARCHITECTURE.md. This makes the citation system work for both PDFs
    (which have pages) and Markdown (which doesn't).
    """

    model_config = ConfigDict(frozen=True)

    document_id: str
    paragraph_index: int = Field(ge=0)
    paragraph_text: str = Field(min_length=1)
    similarity: float = Field(ge=0.0, le=1.0, default=1.0)


# ---------------------------------------------------------------------------
# Tenders, bids, documents
# ---------------------------------------------------------------------------


class Tender(BaseModel):
    """A tender document and its extracted criteria."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    issuer: str
    country_code: str
    document_path: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Bid(BaseModel):
    """A bid submitted against a tender."""

    model_config = ConfigDict(frozen=True)

    id: str
    tender_id: str
    bidder_name: str
    document_path: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Document(BaseModel):
    """A parsed document (tender or bid) with paragraph-level chunks.

    Every citation points to a paragraph in a Document.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["tender", "bid"]
    parent_id: str  # tender_id or bid_id
    source_path: str
    paragraphs: list[str] = Field(min_length=1)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Criteria, responses, scores, risk flags
# ---------------------------------------------------------------------------


class CriterionCategory(str, Enum):
    ELIGIBILITY = "eligibility"
    TECHNICAL = "technical"
    FINANCIAL = "financial"
    MANDATORY_DOCUMENT = "mandatory_document"
    COMPLIANCE = "compliance"
    OTHER = "other"


class Criterion(BaseModel):
    """An evaluation criterion extracted from the tender."""

    model_config = ConfigDict(frozen=True)

    id: str
    tender_id: str
    name: str
    description: str
    category: CriterionCategory
    weight: float = Field(ge=0.0, le=1.0, default=0.2)
    mandatory: bool = False
    citation: Citation
    ai_generated: bool = True


class BidResponse(BaseModel):
    """A bid's response to a specific criterion — extracted from the bid doc."""

    model_config = ConfigDict(frozen=True)

    id: str
    bid_id: str
    criterion_id: str
    response_text: str
    citation: Citation
    ai_generated: bool = True


class Score(BaseModel):
    """A score for a (bid, criterion) pair."""

    model_config = ConfigDict(frozen=True)

    id: str
    bid_id: str
    criterion_id: str
    score: float = Field(ge=0.0, le=10.0)
    rationale: str
    citation_tender: Citation
    citation_bid: Citation
    ai_generated: bool = True


class RiskFlag(BaseModel):
    """A compliance risk flag for a bid."""

    model_config = ConfigDict(frozen=True)

    id: str
    bid_id: str
    risk_type: str  # "missing_mandatory_document", "anomalous_low_financial", etc.
    severity: Literal["info", "warning", "critical"]
    description: str
    citation: Citation
    ai_generated: bool = True


# ---------------------------------------------------------------------------
# Reports and decisions
# ---------------------------------------------------------------------------


class BidEvaluation(BaseModel):
    """The evaluation of one bid: scores + risk flags + a recommendation."""

    model_config = ConfigDict(frozen=True)

    bid_id: str
    bidder_name: str
    total_score: float = Field(ge=0.0)
    weighted_score: float = Field(ge=0.0)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    recommendation: Literal["award", "shortlist", "reject"]
    recommendation_rationale: str


class Report(BaseModel):
    """A composed evaluation report for a tender.

    Immutable. Stamped `ai_generated=True`. The procurement officer
    reviews this and records `Decision`s separately.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    tender_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    bids: list[BidEvaluation] = Field(default_factory=list)
    ai_generated: bool = True
    correlation_id: str = ""
    token_cost_cents: Decimal = Decimal("0")


class DecisionType(str, Enum):
    """The three decisions a procurement officer can record."""

    ACCEPT = "accept"
    REJECT = "reject"
    NEEDS_REVIEW = "needs_review"


class Decision(BaseModel):
    """A procurement officer's decision on a bid.

    HUMAN-ONLY. The agent cannot create a Decision — see ARCHITECTURE.md §5.
    The SQL schema enforces this with a CHECK constraint and a trigger.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    tender_id: str
    bid_id: str
    decision: DecisionType
    rationale: str
    decided_by: str  # must NOT be 'agent'
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


class AuditEntry(BaseModel):
    """One entry in the audit trail.

    Every AI proposal and every human decision produces an AuditEntry.
    The trail is exportable as a signed PDF for the procurement archive.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    tender_id: str
    bid_id: str | None
    entry_kind: Literal["ai_proposal", "human_decision", "tool_call"]
    actor: str
    actor_kind: PrincipalKind
    payload: dict
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
