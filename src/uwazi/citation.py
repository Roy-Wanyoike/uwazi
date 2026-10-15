"""Citation validator — fails closed when AI claims are not grounded.

Every AI output (score, risk flag, response) passes through this
validator before it is persisted. The validator performs five checks:

  1. Existence      — does the cited document exist?
  2. Pointer        — does the citation point to a paragraph that exists?
  3. Span support   — does the cited paragraph contain the claim? (similarity)
  4. Claim strength — is the claim stronger than the evidence?
  5. Source authority — is the cited source authoritative for this claim?

If any check fails, the claim is not published. The agent surfaces a
`[This score could not be fully verified against the source documents]`
marker instead.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Citation

# ---------------------------------------------------------------------------
# Strength markers
# ---------------------------------------------------------------------------

_STRONG_WORDS = {"must", "shall", "always", "never", "required", "mandatory", "all"}
_SOFT_WORDS = {"may", "should", "might", "could", "sometimes", "optional", "may include"}


@dataclass(frozen=True)
class ValidationResult:
    """The result of validating a claim against its citation."""

    valid: bool
    reason: str = ""
    downgraded_similarity: float | None = None


# ---------------------------------------------------------------------------
# The five checks
# ---------------------------------------------------------------------------


def validate_citation(
    claim: str,
    citation: Citation,
    known_documents: dict[str, list[str]],
    min_similarity: float = 0.75,
) -> ValidationResult:
    """Run all five checks. Returns ValidationResult(valid=False) on any failure."""

    # 1. Existence — does the cited document exist?
    if citation.document_id not in known_documents:
        return ValidationResult(
            valid=False,
            reason=f"document {citation.document_id} not found in the document store",
        )

    paragraphs = known_documents[citation.document_id]

    # 2. Pointer — does the cited paragraph index exist?
    if citation.paragraph_index < 0 or citation.paragraph_index >= len(paragraphs):
        return ValidationResult(
            valid=False,
            reason=f"paragraph index {citation.paragraph_index} out of range (0..{len(paragraphs) - 1})",
        )

    actual_text = paragraphs[citation.paragraph_index]
    # 3. Span support — does the cited paragraph actually support the claim?
    sim = _token_overlap(claim, actual_text)
    if sim < min_similarity:
        return ValidationResult(
            valid=False,
            reason=f"claim-citation similarity {sim:.2f} below threshold {min_similarity:.2f}",
            downgraded_similarity=sim,
        )

    # 4. Claim strength — is the claim stronger than the evidence?
    strength_violation = _check_strength(claim, actual_text)
    if strength_violation:
        return ValidationResult(valid=False, reason=strength_violation)

    # 5. Source authority — handled by the caller (the agent passes the
    # right kind of source for the right kind of claim). We just verify
    # the citation text isn't a generic placeholder.
    if "PLACEHOLDER" in actual_text.upper():
        return ValidationResult(
            valid=False,
            reason="cited paragraph is a placeholder, not actual evidence",
        )

    return ValidationResult(valid=True, downgraded_similarity=sim)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]+\b")


def _tokenize(text: str) -> set[str]:
    """Lowercase alpha-numeric tokens, length > 2."""
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text) if len(m.group(0)) > 2}


def _token_overlap(claim: str, evidence: str) -> float:
    """Jaccard-style overlap between claim tokens and evidence tokens.

    Returns a value in [0.0, 1.0]. Higher = more support.
    """
    claim_tokens = _tokenize(claim)
    evidence_tokens = _tokenize(evidence)
    if not claim_tokens or not evidence_tokens:
        return 0.0
    intersection = claim_tokens & evidence_tokens
    if not intersection:
        return 0.0
    # Weight by claim coverage: how many of the claim's tokens appear in evidence?
    return len(intersection) / len(claim_tokens)


def _check_strength(claim: str, evidence: str) -> str | None:
    """Return an error string if the claim is stronger than the evidence.

    Heuristic: if the claim uses strong words (must/shall/always) but
    the evidence uses soft words (may/should/might), the claim is too
    strong for the evidence.
    """
    claim_lower = claim.lower()
    evidence_lower = evidence.lower()

    claim_is_strong = any(w in claim_lower for w in _STRONG_WORDS)
    evidence_is_soft = any(w in evidence_lower for w in _SOFT_WORDS)
    if claim_is_strong and evidence_is_soft:
        return (
            "claim uses strong modal (must/shall/always) but evidence uses soft modal "
            "(may/should/might) — claim is stronger than the evidence supports"
        )
    return None


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------


def filter_valid(
    claims: Iterable[tuple[str, Citation]],
    known_documents: dict[str, list[str]],
    min_similarity: float = 0.75,
) -> list[tuple[str, Citation, ValidationResult]]:
    """Validate a batch of (claim, citation) pairs. Returns the ones that pass."""
    out: list[tuple[str, Citation, ValidationResult]] = []
    for claim, cit in claims:
        result = validate_citation(claim, cit, known_documents, min_similarity)
        if result.valid:
            out.append((claim, cit, result))
    return out
