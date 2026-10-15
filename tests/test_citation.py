"""Tests for the citation validator.

The validator is the gate that prevents hallucinated AI claims from
being published. If any of its five checks fails, the claim is dropped.
"""
from __future__ import annotations

from uwazi.citation import (
    filter_valid,
    validate_citation,
    ValidationResult,
)
from uwazi.models import Citation


def test_valid_citation_passes() -> None:
    docs = {"doc-1": ["The bidder must submit an ISO 9001 certificate."]}
    claim = "The bidder must submit an ISO 9001 certificate."
    cit = Citation(document_id="doc-1", paragraph_index=0, paragraph_text=docs["doc-1"][0], similarity=1.0)
    result = validate_citation(claim, cit, docs, min_similarity=0.5)
    assert result.valid, f"expected valid, got: {result.reason}"


def test_missing_document_fails() -> None:
    docs = {"doc-1": ["one"]}
    claim = "anything"
    cit = Citation(document_id="doc-missing", paragraph_index=0, paragraph_text="one", similarity=1.0)
    result = validate_citation(claim, cit, docs)
    assert not result.valid
    assert "not found" in result.reason


def test_out_of_range_paragraph_fails() -> None:
    docs = {"doc-1": ["only one paragraph"]}
    claim = "only one paragraph"
    cit = Citation(document_id="doc-1", paragraph_index=99, paragraph_text="only one paragraph", similarity=1.0)
    result = validate_citation(claim, cit, docs)
    assert not result.valid
    assert "out of range" in result.reason


def test_low_similarity_fails() -> None:
    docs = {"doc-1": ["The quick brown fox jumps over the lazy dog."]}
    claim = "The bid must include a methodology plan."  # no token overlap
    cit = Citation(document_id="doc-1", paragraph_index=0, paragraph_text=docs["doc-1"][0], similarity=1.0)
    result = validate_citation(claim, cit, docs, min_similarity=0.3)
    assert not result.valid
    assert "below threshold" in result.reason


def test_claim_stronger_than_evidence_fails() -> None:
    docs = {"doc-1": ["The bidder may submit an ISO 9001 certificate."]}
    claim = "The bidder must submit an ISO 9001 certificate."
    cit = Citation(document_id="doc-1", paragraph_index=0, paragraph_text=docs["doc-1"][0], similarity=1.0)
    result = validate_citation(claim, cit, docs, min_similarity=0.5)
    assert not result.valid
    assert "stronger" in result.reason.lower()


def test_filter_valid_drops_invalid() -> None:
    docs = {"doc-1": ["The bidder must submit an ISO 9001 certificate."]}
    claims = [
        ("The bidder must submit an ISO 9001 certificate.",
         Citation(document_id="doc-1", paragraph_index=0, paragraph_text=docs["doc-1"][0], similarity=1.0)),
        ("Hallucinated claim with no overlap.",
         Citation(document_id="doc-1", paragraph_index=0, paragraph_text=docs["doc-1"][0], similarity=1.0)),
    ]
    valid = filter_valid(claims, docs, min_similarity=0.5)
    assert len(valid) == 1
    assert valid[0][0].startswith("The bidder must")
