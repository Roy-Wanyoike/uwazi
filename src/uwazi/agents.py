"""The four single-purpose agents.

  ExtractorAgent      — extracts criteria from a tender document.
  BidAnalyzerAgent    — extracts bid responses per criterion.
  ScorerAgent         — scores each (bid, criterion) pair.
  RiskAgent           — flags compliance risks per bid.

Each agent:
  - Takes a single well-typed input.
  - Calls the LLM gateway with one prompt (no chain-of-thought).
  - Parses the LLM response into a strict JSON shape.
  - Returns typed data the orchestrator can pass to the next agent.

None of the agents writes to the database. The orchestrator is the only
entity that persists, and it does so via the MCP tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .gateway import Gateway, LLMResponse
from .prompts import (
    ANALYZER_SYSTEM,
    EXTRACTOR_SYSTEM,
    RISK_SYSTEM,
    SCORER_SYSTEM,
    analyzer_user,
    extractor_user,
    risk_user,
    scorer_user,
)

# ---------------------------------------------------------------------------
# JSON parsing — strict, no backticks, no prose
# ---------------------------------------------------------------------------


def _parse_json(response: LLMResponse) -> dict[str, Any]:
    """Parse a JSON response from the LLM, raising on malformed output.

    Strips a markdown code fence if the LLM ignored instructions and
    wrapped the JSON in ```json ... ```.
    """
    text = response.content.strip()
    if text.startswith("```"):
        # Strip the opening fence (```json or ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        # Strip the closing fence
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentError(
            f"LLM returned non-JSON response (stubbed={response.stubbed}): "
            f"{response.content[:200]}..."
        ) from exc
    if not isinstance(data, dict):
        raise AgentError("LLM returned JSON that is not an object")
    return data


class AgentError(Exception):
    """Raised when an agent's LLM response cannot be parsed or violates the contract."""


# ---------------------------------------------------------------------------
# ExtractorAgent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractorOutput:
    criteria: list[dict[str, Any]]
    tokens_used: int
    cost_cents: Decimal


class ExtractorAgent:
    """Extracts evaluation criteria from a tender document."""

    name = "extractor"
    version = "0.1.0"

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway

    async def run(
        self,
        tender_title: str,
        tender_paragraphs: list[str],
    ) -> ExtractorOutput:
        system = EXTRACTOR_SYSTEM
        user = extractor_user(tender_title, tender_paragraphs)
        response = await self._gateway.complete(system, user, max_tokens=2048, temperature=0.0)
        data = _parse_json(response)
        criteria = data.get("criteria", [])
        if not isinstance(criteria, list):
            raise AgentError("extractor: 'criteria' is not a list")
        return ExtractorOutput(
            criteria=criteria,
            tokens_used=response.total_tokens,
            cost_cents=response.cost_cents,
        )


# ---------------------------------------------------------------------------
# BidAnalyzerAgent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalyzerOutput:
    responses: list[dict[str, Any]]
    tokens_used: int
    cost_cents: Decimal


class BidAnalyzerAgent:
    """Extracts a bid's responses to each criterion."""

    name = "analyzer"
    version = "0.1.0"

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway

    async def run(
        self,
        bidder_name: str,
        bid_paragraphs: list[str],
        criteria: list[dict[str, Any]],
    ) -> AnalyzerOutput:
        system = ANALYZER_SYSTEM
        user = analyzer_user(bidder_name, bid_paragraphs, criteria)
        response = await self._gateway.complete(system, user, max_tokens=2048, temperature=0.0)
        data = _parse_json(response)
        responses = data.get("responses", [])
        if not isinstance(responses, list):
            raise AgentError("analyzer: 'responses' is not a list")
        return AnalyzerOutput(
            responses=responses,
            tokens_used=response.total_tokens,
            cost_cents=response.cost_cents,
        )


# ---------------------------------------------------------------------------
# ScorerAgent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScorerOutput:
    scores: list[dict[str, Any]]
    tokens_used: int
    cost_cents: Decimal


class ScorerAgent:
    """Scores each (bid, criterion) pair on a 0-10 scale."""

    name = "scorer"
    version = "0.1.0"

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway

    async def run(
        self,
        bidder_name: str,
        criteria_with_responses: list[dict[str, Any]],
    ) -> ScorerOutput:
        system = SCORER_SYSTEM
        user = scorer_user(bidder_name, criteria_with_responses)
        response = await self._gateway.complete(system, user, max_tokens=2048, temperature=0.0)
        data = _parse_json(response)
        scores = data.get("scores", [])
        if not isinstance(scores, list):
            raise AgentError("scorer: 'scores' is not a list")
        # Validate scores are in [0, 10]
        for s in scores:
            score = float(s.get("score", 0))
            if score < 0 or score > 10:
                raise AgentError(f"scorer: score {score} out of [0,10]")
        return ScorerOutput(
            scores=scores,
            tokens_used=response.total_tokens,
            cost_cents=response.cost_cents,
        )


# ---------------------------------------------------------------------------
# RiskAgent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskOutput:
    risk_flags: list[dict[str, Any]]
    tokens_used: int
    cost_cents: Decimal


class RiskAgent:
    """Flags compliance risks per bid."""

    name = "risk"
    version = "0.1.0"

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway

    async def run(
        self,
        bidder_name: str,
        bid_paragraphs: list[str],
        mandatory_criteria: list[dict[str, Any]],
        financial_quote: str | None,
    ) -> RiskOutput:
        system = RISK_SYSTEM
        user = risk_user(bidder_name, bid_paragraphs, mandatory_criteria, financial_quote)
        response = await self._gateway.complete(system, user, max_tokens=2048, temperature=0.0)
        data = _parse_json(response)
        risk_flags = data.get("risk_flags", [])
        if not isinstance(risk_flags, list):
            raise AgentError("risk: 'risk_flags' is not a list")
        # Validate severities
        valid_severities = {"info", "warning", "critical"}
        for r in risk_flags:
            sev = r.get("severity", "info")
            if sev not in valid_severities:
                raise AgentError(f"risk: severity {sev!r} not in {valid_severities}")
        return RiskOutput(
            risk_flags=risk_flags,
            tokens_used=response.total_tokens,
            cost_cents=response.cost_cents,
        )
