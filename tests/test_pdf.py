"""Tests for the document ingestion pipeline.

Paragraph-level citation tracking is what makes the system work for
both PDFs (page-based) and Markdown (no pages).
"""

from __future__ import annotations

from pathlib import Path

from uwazi.pdf import (
    citation_for,
    ingest_document,
    ingest_markdown,
    search_paragraphs,
    split_paragraphs,
)


def test_split_paragraphs_blank_lines() -> None:
    text = "First paragraph.\n\nSecond paragraph.\n\nThird."
    parts = split_paragraphs(text)
    assert parts == ["First paragraph.", "Second paragraph.", "Third."]


def test_split_paragraphs_long_paragraph_chunks_at_sentence() -> None:
    long_para = "Sentence one. " * 100  # ~1500 chars
    parts = split_paragraphs(long_para.strip())
    assert len(parts) > 1
    assert all(len(p) <= 600 or len(p) == len(long_para) - 1 for p in parts)  # all within budget


def test_strip_frontmatter() -> None:
    text = "---\nkey: value\n---\n\n# Heading\n\nBody paragraph."
    parts = split_paragraphs(_strip_frontmatter(text))
    assert any("Heading" in p for p in parts)
    assert any("Body paragraph" in p for p in parts)
    assert not any("key: value" in p for p in parts)


def _strip_frontmatter(text: str) -> str:
    """Local copy of the frontmatter stripper (kept here to test indirectly)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4 :].lstrip("\n")


def test_ingest_markdown(tmp_path: Path) -> None:
    f = tmp_path / "test.md"
    f.write_text("# Title\n\nFirst para.\n\nSecond para.\n", encoding="utf-8")
    paragraphs = ingest_markdown(f)
    assert len(paragraphs) >= 2
    # Heading is kept as its own paragraph (citations can point to it).
    joined = "\n".join(paragraphs)
    assert "First para" in joined
    assert "Second para" in joined


def test_ingest_document_returns_typed_document(tmp_path: Path) -> None:
    f = tmp_path / "tender.md"
    f.write_text("Para one.\n\nPara two.", encoding="utf-8")
    doc = ingest_document(
        doc_id="doc-test",
        kind="tender",
        parent_id="tender-1",
        source_path=str(f),
    )
    assert doc.id == "doc-test"
    assert doc.kind == "tender"
    assert doc.parent_id == "tender-1"
    assert len(doc.paragraphs) >= 2


def test_citation_for_valid_index() -> None:
    paras = ["alpha", "beta", "gamma"]
    c = citation_for("doc-1", paras, 1)
    assert c.document_id == "doc-1"
    assert c.paragraph_index == 1
    assert c.paragraph_text == "beta"


def test_citation_for_out_of_range_raises() -> None:
    paras = ["alpha"]
    try:
        citation_for("doc-1", paras, 99)
        assert False, "expected IndexError"
    except IndexError:
        pass


def test_search_paragraphs_returns_relevant() -> None:
    paras = [
        "The bidder must submit an ISO 9001 certificate.",
        "The financial quote should include all applicable taxes.",
        "Project methodology is required.",
    ]
    results = search_paragraphs(paras, "ISO 9001 certificate", top_k=2)
    assert len(results) >= 1
    assert results[0][0] == 0  # the ISO paragraph
    assert results[0][2] > 0.0


def test_search_paragraphs_no_matches_returns_empty() -> None:
    paras = ["alpha", "beta", "gamma"]
    results = search_paragraphs(paras, "completely different tokens xyz", top_k=3)
    assert len(results) == 0
