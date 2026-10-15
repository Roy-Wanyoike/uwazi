"""Provider-agnostic LLM gateway.

Uwazi uses the `openai` SDK pointed at any OpenAI-compatible endpoint:
OpenAI, Qwen via ModelScope, OpenRouter, or a local Llama server (vllm).

When `OPENAI_API_KEY` is unset, the gateway runs in STUB mode: it
returns deterministic canned responses. This makes the demo work
offline and makes the test suite fast.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from .config import LLMConfig


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMResponse:
    """A response from the LLM gateway."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    cost_cents: Decimal
    model: str
    stubbed: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# ---------------------------------------------------------------------------
# Protocol — what agents may call
# ---------------------------------------------------------------------------


class ModelClient(Protocol):
    """The minimal model-gateway interface agents may use.

    Real impl = `Gateway`. Tests substitute a stub.
    """

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        ...


# ---------------------------------------------------------------------------
# Gateway — provider-agnostic LLM client
# ---------------------------------------------------------------------------


class Gateway:
    """The real model gateway.

    Uses the `openai` SDK to call any OpenAI-compatible endpoint.
    When `stub_mode=True`, returns deterministic canned responses.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client: Any = None
        if not config.stub_mode:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=config.api_key,
                    base_url=config.base_url,
                )
            except ImportError as exc:
                raise RuntimeError(
                    "openai package not installed — run `pip install openai` "
                    "or set OPENAI_API_KEY to empty to use stub mode"
                ) from exc

    @property
    def stub_mode(self) -> bool:
        return self._config.stub_mode

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Call the LLM. Returns an LLMResponse with cost + token accounting."""
        if self._config.stub_mode:
            return self._stub_complete(system_prompt, user_prompt, max_tokens)

        try:
            resp = await self._client.chat.completions.create(  # type: ignore[union-attr]
                model=self._config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            # Fail closed — return a stub response rather than crash the workflow.
            return LLMResponse(
                content=f"[LLM call failed: {exc}]",
                prompt_tokens=0,
                completion_tokens=0,
                cost_cents=Decimal("0"),
                model=self._config.model,
                stubbed=True,
            )

        content = resp.choices[0].message.content or ""
        prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        completion_tokens = resp.usage.completion_tokens if resp.usage else 0

        # Rough cost estimate — OpenAI gpt-4o-mini pricing.
        # For Qwen / other providers, this is an upper-bound estimate.
        cost_cents = Decimal(prompt_tokens) * Decimal("0.00015") + Decimal(
            completion_tokens
        ) * Decimal("0.00060")

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_cents=cost_cents,
            model=self._config.model,
        )

    # ------------------------------------------------------------------
    # Stub mode — deterministic canned responses for offline / tests
    # ------------------------------------------------------------------

    def _stub_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> LLMResponse:
        """Return a deterministic stub response.

        The stub inspects the system prompt to figure out which agent
        is calling and returns canned JSON. This makes the test suite
        fast and reproducible without any network calls.
        """
        sys_lower = system_prompt.lower()

        if "extractor" in sys_lower or "extract criteria" in sys_lower:
            content = json.dumps({
                "criteria": [
                    {
                        "name": "Technical Capacity",
                        "description": "Bidder must demonstrate prior experience in similar projects.",
                        "category": "technical",
                        "weight": 0.25,
                        "mandatory": False,
                        "citation_paragraph": 1,
                    },
                    {
                        "name": "ISO 9001 Certification",
                        "description": "Bidder must submit a valid ISO 9001 certificate.",
                        "category": "mandatory_document",
                        "weight": 0.10,
                        "mandatory": True,
                        "citation_paragraph": 2,
                    },
                    {
                        "name": "Financial Quote",
                        "description": "Bidder must submit a complete financial quote.",
                        "category": "financial",
                        "weight": 0.35,
                        "mandatory": False,
                        "citation_paragraph": 3,
                    },
                    {
                        "name": "Eligibility — Registered Company",
                        "description": "Bidder must be a registered company in the relevant jurisdiction.",
                        "category": "eligibility",
                        "weight": 0.10,
                        "mandatory": True,
                        "citation_paragraph": 0,
                    },
                    {
                        "name": "Compliance — Tax Compliance Certificate",
                        "description": "Bidder must submit a valid Tax Compliance Certificate.",
                        "category": "compliance",
                        "weight": 0.10,
                        "mandatory": True,
                        "citation_paragraph": 4,
                    },
                    {
                        "name": "Project Methodology",
                        "description": "Bidder must submit a project methodology and timeline.",
                        "category": "technical",
                        "weight": 0.10,
                        "mandatory": False,
                        "citation_paragraph": 5,
                    },
                ]
            })
        elif "analyzer" in sys_lower or "bid response" in sys_lower:
            content = json.dumps({
                "responses": [
                    {"criterion_name": "Technical Capacity",
                     "response_text": "The bidder claims 5 years of experience in water reticulation projects.",
                     "citation_paragraph": 1},
                    {"criterion_name": "ISO 9001 Certification",
                     "response_text": "The bid does not contain an ISO 9001 certificate.",
                     "citation_paragraph": 0},
                    {"criterion_name": "Financial Quote",
                     "response_text": "The bidder quotes KES 18,500,000 for the works.",
                     "citation_paragraph": 3},
                    {"criterion_name": "Eligibility — Registered Company",
                     "response_text": "The bidder is registered as AquaForce Ltd, registration CPR/2020/45678.",
                     "citation_paragraph": 0},
                    {"criterion_name": "Compliance — Tax Compliance Certificate",
                     "response_text": "The bidder submits a valid Tax Compliance Certificate dated 2026-09-30.",
                     "citation_paragraph": 4},
                    {"criterion_name": "Project Methodology",
                     "response_text": "The bidder submits a 4-phase methodology with a 24-week timeline.",
                     "citation_paragraph": 5},
                ]
            })
        elif "scorer" in sys_lower or "score this" in sys_lower:
            content = json.dumps({
                "scores": [
                    {"criterion_name": "Technical Capacity", "score": 8.0,
                     "rationale": "Bidder demonstrates 5+ years of relevant experience."},
                    {"criterion_name": "ISO 9001 Certification", "score": 0.0,
                     "rationale": "Mandatory document not submitted — score is zero per the rubric."},
                    {"criterion_name": "Financial Quote", "score": 7.0,
                     "rationale": "Quote is reasonable and within the estimated range."},
                    {"criterion_name": "Eligibility — Registered Company", "score": 10.0,
                     "rationale": "Company registration confirmed."},
                    {"criterion_name": "Compliance — Tax Compliance Certificate", "score": 9.0,
                     "rationale": "Valid TCC submitted, current as of 2026-09-30."},
                    {"criterion_name": "Project Methodology", "score": 7.0,
                     "rationale": "4-phase methodology with realistic timeline."},
                ]
            })
        elif "risk" in sys_lower or "compliance risk" in sys_lower:
            content = json.dumps({
                "risk_flags": [
                    {"risk_type": "anomalous_low_financial",
                     "severity": "critical",
                     "description": "The financial quote is 60% below the next-lowest bid — possible abnormally low bid per regulation 47.",
                     "citation_paragraph": 3}
                ]
            })
        else:
            # Generic stub — return a minimal valid JSON.
            content = json.dumps({"answer": "stub", "citations": []})

        return LLMResponse(
            content=content,
            prompt_tokens=len(system_prompt.split()) + len(user_prompt.split()),
            completion_tokens=len(content.split()),
            cost_cents=Decimal("0"),
            model=self._config.model if self._config.stub_mode else self._config.model,
            stubbed=True,
        )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_gateway(config: LLMConfig | None = None) -> Gateway:
    """Build a Gateway from the given (or default) LLMConfig."""
    return Gateway(config or LLMConfig())
