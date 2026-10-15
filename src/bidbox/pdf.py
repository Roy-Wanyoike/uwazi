"""Document ingestion — PDF and Markdown, with paragraph-level citation tracking.

The citation system is paragraph-based (see ADR-0002 in ARCHITECTURE.md).
This makes the system work for both PDFs (which have pages) and Markdown
(which doesn't). A citation is `(document_id, paragraph_index)`.

For PDFs, we use pdfplumber to extract text per page, then split each
page into paragraphs at double-newlines. For Markdown, we split at
blank lines. In both cases, we end up with `list[str]` — paragraphs.

Paragraphs are kept short (under ~500 chars where possible) so that
citations are precise: a single citation points to one paragraph, not
a whole page.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .models import Citation, Document


# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------


def split_paragraphs(text: str) -> list[str]:
    """Split a body of text into citation-grain paragraphs.

    Heuristic: split at blank lines, then split any resulting paragraph
    that is longer than MAX_PARAGRAPH_CHARS into smaller chunks at the
    nearest sentence boundary. This keeps citations precise.
    """
    MAX_PARAGRAPH_CHARS = 600

    raw = [p.strip() for p in text.split("\n\n") if p.strip()]
    paragraphs: list[str] = []
    for chunk in raw:
        if len(chunk) <= MAX_PARAGRAPH_CHARS:
            paragraphs.append(chunk)
            continue
        # Chunk is too long — split at sentence boundaries.
        parts = _split_at_sentences(chunk, MAX_PARAGRAPH_CHARS)
        paragraphs.extend(parts)
    return paragraphs


def _split_at_sentences(text: str, max_chars: int) -> list[str]:
    """Split a long paragraph at sentence boundaries, respecting max_chars."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[str] = []
    buf: str = ""
    for s in sentences:
        if not s:
            continue
        if len(buf) + len(s) + 1 <= max_chars:
            buf = (buf + " " + s).strip() if buf else s
        else:
            if buf:
                out.append(buf)
            # Sentence itself might be longer than max_chars — hard split.
            while len(s) > max_chars:
                out.append(s[:max_chars])
                s = s[max_chars:]
            buf = s
    if buf:
        out.append(buf)
    return out


# ---------------------------------------------------------------------------
# Markdown ingestion
# ---------------------------------------------------------------------------


def ingest_markdown(path: str | Path) -> list[str]:
    """Read a Markdown file and split into paragraphs.

    Markdown files are the simpler case — they are already plain text.
    We strip frontmatter (YAML between --- markers) before splitting.
    """
    text = Path(path).read_text(encoding="utf-8")
    text = _strip_frontmatter(text)
    return split_paragraphs(text)


def _strip_frontmatter(text: str) -> str:
    """Remove a YAML frontmatter block (--- ... ---) from the top of a Markdown file."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4 :].lstrip("\n")


# ---------------------------------------------------------------------------
# PDF ingestion
# ---------------------------------------------------------------------------


def ingest_pdf(path: str | Path) -> list[str]:
    """Read a PDF file and split into paragraphs.

    Uses pdfplumber to extract per-page text, then splits at blank lines.
    Each paragraph is tagged with the page number in the Document
    metadata so citations can resolve back to a specific page.
    """
    import pdfplumber  # local import — keeps the module loadable without the dep

    paragraphs: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            if not page_text.strip():
                continue
            page_text = f"[Page {page_num}]\n{page_text}"
            for chunk in split_paragraphs(page_text):
                paragraphs.append(chunk)
    return paragraphs


# ---------------------------------------------------------------------------
# Unified ingest — file-type dispatch
# ---------------------------------------------------------------------------


def ingest_document(
    doc_id: str,
    kind: str,
    parent_id: str,
    source_path: str | Path,
) -> Document:
    """Ingest a document (PDF or Markdown), returning a Document with paragraphs.

    The returned Document is ready to be stored via `db.save_document`.
    Citations point to paragraph indexes in `Document.paragraphs`.
    """
    path = Path(source_path)
    suffix = path.suffix.lower()
    if suffix == ".md":
        paragraphs = ingest_markdown(path)
    elif suffix == ".pdf":
        paragraphs = ingest_pdf(path)
    elif suffix in (".txt", ".text"):
        paragraphs = split_paragraphs(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"unsupported document format: {suffix!r} ({path})")

    if not paragraphs:
        raise ValueError(f"no text extracted from {path}")

    return Document(
        id=doc_id,
        kind=kind,  # type: ignore[arg-type]
        parent_id=parent_id,
        source_path=str(path),
        paragraphs=paragraphs,
    )


# ---------------------------------------------------------------------------
# Citation builder
# ---------------------------------------------------------------------------


def citation_for(document_id: str, paragraphs: list[str], index: int) -> Citation:
    """Build a Citation for a specific paragraph index.

    `similarity` defaults to 1.0 for direct citations — i.e., the agent
    pulled the text directly from the paragraph. The citation validator
    may downgrade this to a lower similarity if the claim is paraphrased.
    """
    if index < 0 or index >= len(paragraphs):
        raise IndexError(f"paragraph index {index} out of range (0..{len(paragraphs) - 1})")
    return Citation(
        document_id=document_id,
        paragraph_index=index,
        paragraph_text=paragraphs[index],
        similarity=1.0,
    )


def search_paragraphs(paragraphs: list[str], query: str, top_k: int = 3) -> list[tuple[int, str, float]]:
    """Find the top-k paragraphs most relevant to a query.

    Uses a simple token-overlap similarity (TF weighted). For production
    at scale, swap for an embedding-based search (see ADR-0009 in
    ARCHITECTURE.md of Civic Intelligence — the same pattern).
    """
    query_tokens = {w.lower().strip(".,();:[]{}\"'") for w in query.split() if len(w) > 2}
    if not query_tokens:
        return [(i, p, 0.0) for i, p in enumerate(paragraphs[:top_k])]

    scored: list[tuple[int, str, float]] = []
    for i, p in enumerate(paragraphs):
        para_tokens = [w.lower().strip(".,();:[]{}\"'") for w in p.split()]
        if not para_tokens:
            continue
        hits = sum(1 for t in para_tokens if t in query_tokens)
        score = hits / len(para_tokens)  # simple TF
        if hits > 0:
            scored.append((i, p, score))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:top_k]
