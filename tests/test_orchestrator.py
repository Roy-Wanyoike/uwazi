"""Regression tests for report composition."""

from __future__ import annotations

from typing import cast

import pytest

from uwazi.orchestrator import UwaziGraph, UwaziState


@pytest.mark.asyncio
async def test_weighted_score_matches_criteria_by_name_not_list_order() -> None:
    graph = object.__new__(UwaziGraph)
    state = {
        "tender": {"id": "t1"},
        "bids": [{"bid_id": "b1", "bidder_name": "Bidder", "paragraphs": []}],
        "criteria": [
            {"name": "Technical", "weight": 0.75, "mandatory": False},
            {"name": "Financial", "weight": 0.25, "mandatory": False},
        ],
        "scores": {
            "b1": [
                {"criterion_name": "Financial", "score": 2.0},
                {"criterion_name": "Technical", "score": 8.0},
            ]
        },
        "risk_flags": {"b1": []},
    }

    result = await graph._compose_report(cast(UwaziState, state))

    assert result["report"]["bids"][0]["weighted_score"] == pytest.approx(6.5)
